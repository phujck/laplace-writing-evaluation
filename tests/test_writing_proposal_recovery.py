"""Real journal/process-loss/source-door checks; no provider or live project writes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from laplace.projects import library as writing_projects
from laplace.native import tools as writing_tools
from laplace.manuscript import manuscript_proposals
from laplace.writing import turn_admission
from laplace.writing import records as writing_records
from laplace.writing import session_reads
from laplace.manuscript import source_application
from laplace.writing import turn_jobs
from laplace.writing.records import _fold as records_fold
from laplace.pipeline import authoring

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def clear_runtime():
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()
    yield
    records_fold._CACHE.clear()
    turn_jobs._JOBS.clear()


def prepare(root: Path):
    source = root / 'source'
    source.mkdir(parents=True)
    file = source / 'Book.tex'
    file.write_text('\\documentclass{article}\n\\begin{document}\nOriginal prose.\n\\end{document}\n')
    code, value = writing_projects.import_source({
        'name': 'recovery', 'title': 'Recovery', 'root': 'source/Book.tex', 'editable': True}, root)
    assert code == 201, value
    context = authoring.build_context('recovery', {'files': ['Book.tex']}, root)
    session = turn_admission.new_session(root, 'recovery', 'codex', 'not-invoked', 'low')
    turn_id = 'WT-recovery'
    writing_records.bank(root, {'record': 'writing-turn', 'id': turn_id, 'session_id': session['id'],
        'project': 'recovery', 'request_id': 'recovery-request', 'text': 'Revise this sentence.',
        'mode': 'work', 'selection': {'files': ['Book.tex']},
        'context_id': context['context_id'], 'dependencies': context['dependencies'],
        'document': context['document'], 'consumed': context['consumed']})
    proposed = {'answer': 'A saved sentence revision.', 'edits': [{
        'file': 'Book.tex', 'line_start': 3, 'line_end': 3, 'before': 'Original prose.',
        'after': 'Revised prose.', 'reason': 'Requested revision.'}]}
    result = writing_tools.execute(root, 'recovery', 'work', 'propose_revision', proposed, turn_id)
    assert result['ok'] is True, result
    return file, session['id'], turn_id, proposed


def rows(root):
    return [json.loads(line) for line in (root / 'contract/talk.jsonl').read_text().splitlines()]


def test_process_dies_after_banking_then_recovers_and_applies_once(tmp_path):
    # A separate interpreter banks through the real tool and exits before a
    # writing-reply. The parent has no session cache or active job to inherit.
    program = """
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'tests'))
from test_writing_proposal_recovery import prepare
prepare(Path(sys.argv[1]))
os._exit(17)
"""
    child = subprocess.run([str(ROOT / 'scripts/laplace-python'), '-c', program, str(tmp_path)],
                           cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert child.returncode == 17, child.stderr
    saved = rows(tmp_path)
    assert not any(row['record'] == 'writing-reply' for row in saved)
    turn = next(row for row in saved if row['record'] == 'writing-turn')
    source = tmp_path / 'source/Book.tex'
    assert 'Original prose.' in source.read_text()

    recovered = session_reads.session_state(tmp_path, turn['session_id'])
    candidate = recovered['turns'][0]
    assert candidate['proposal_state'] == 'saved-without-final-reply'
    assert candidate['proposal']['edits'][0]['after'] == 'Revised prose.'
    assert not candidate.get('reply') and recovered['active'] is None
    index = session_reads.pending_proposals(tmp_path, 'recovery', summary=True)
    assert index['count'] == 1
    assert 'proposal' not in index['proposals'][0] and 'reply' not in index['proposals'][0]
    selected = writing_tools.call(tmp_path,'recovery','review',index['proposals'][0]['read_handle']['native_request'])['owner_response']
    detail = writing_tools.call(tmp_path,'recovery','review',selected['edits'][0]['read_handle']['native_request'])['owner_response']
    # The edit view pins the proposed text by hash; its exact text is the 'proposed' part read.
    after = candidate['proposal']['edits'][0]['after']
    assert 'after' not in detail['edits'][0]
    assert detail['edits'][0]['after_sha256'] == hashlib.sha256(after.encode()).hexdigest()
    proposed = writing_tools.call(tmp_path,'recovery','review',detail['edits'][0]['text_reads']['proposed']['native_request'])['owner_response']
    assert (proposed['part'], proposed['content'], proposed['coverage']['complete']) == ('proposed', after, True)
    assert proposed['coverage']['sha256'] == 'sha256:' + detail['edits'][0]['after_sha256']
    version=selected['proposal_version']
    assert not any(row['record'] == 'writing-reply' for row in rows(tmp_path))

    # Exercise the real source rewrite, feedback and editor-save doors. No
    # mocked adjudicator substitutes for their behavior.
    applied = source_application.apply_proposal(tmp_path, {'project': 'recovery', 'turn_id': turn['id'],'proposal_version':version})
    assert applied['complete'], applied
    assert applied['receipts'][0]['version_id']
    assert 'Revised prose.' in source.read_text()
    feedback = [json.loads(line) for line in (source.parent / 'feedback/feedback.jsonl').read_text().splitlines()]
    assert feedback[-1]['kind'] == 'author-rewrite'
    assert feedback[-1]['by'] == 'author:accepted-model'
    records_fold._CACHE.clear()
    again = source_application.apply_proposal(tmp_path, {'project': 'recovery', 'turn_id': turn['id'],'proposal_version':version})
    assert again['reused'] and again['id'] == applied['id']
    assert len([row for row in rows(tmp_path) if row['record'] == 'writing-application']) == 1
    assert session_reads.pending_proposals(tmp_path, 'recovery')['count'] == 0


def test_active_saved_proposal_is_reviewable_but_requires_its_exact_version(tmp_path):
    from laplace.manuscript import manuscript_proposals
    file, session_id, turn_id, _ = prepare(tmp_path)
    turn_jobs._JOBS[turn_id] = {'done': False}
    assert session_reads.pending_proposals(tmp_path, 'recovery')['proposals'][0]['proposal_state'] == 'ready'
    with pytest.raises(ValueError, match='still working'):
        source_application.apply_proposal(tmp_path, {'project': 'recovery', 'turn_id': turn_id})
    preview=manuscript_proposals.preview(tmp_path,'recovery',turn_id)
    decision={'project':'recovery','turn_id':turn_id,'edit_id':preview['edits'][0]['edit_id'],'decision':'accept'}
    with pytest.raises(ValueError,match='Refresh the saved suggestion'):
        manuscript_proposals.decide(tmp_path,'recovery',decision)
    assert 'Original prose.' in file.read_text()
    assert not any(row['record'] == 'writing-application' for row in rows(tmp_path))
    applied=manuscript_proposals.decide(tmp_path,'recovery',{**decision,'proposal_version':preview['proposal_version']})
    assert applied['application']['complete'] and 'Revised prose.' in file.read_text()
    assert turn_jobs._JOBS[turn_id]['done'] is False


def test_recovered_draft_keeps_changed_source_guard(tmp_path):
    file, _, turn_id, _ = prepare(tmp_path)
    version=manuscript_proposals.preview(tmp_path,'recovery',turn_id)['proposal_version']
    file.write_text(file.read_text().replace('Original prose.', 'A concurrent author edit.'))
    records_fold._CACHE.clear()
    assert session_reads.pending_proposals(tmp_path, 'recovery')['count'] == 1
    with pytest.raises(ValueError, match='changed'):
        source_application.apply_proposal(tmp_path, {'project': 'recovery', 'turn_id': turn_id,'proposal_version':version})
    assert 'A concurrent author edit.' in file.read_text()
    assert not any(row['record'] == 'writing-application' for row in rows(tmp_path))


def test_failed_reply_and_empty_terminal_preserve_candidate_until_exact_rejection(tmp_path):
    _, session_id, turn_id, _ = prepare(tmp_path)
    writing_records.bank(tmp_path, {'record': 'writing-reply', 'id': 'WR-failed', 'turn_id': turn_id,
        'session_id': session_id, 'project': 'recovery', 'status': 'failed', 'text': 'Connection lost.'})
    assert session_reads.pending_proposals(tmp_path, 'recovery')['proposals'][0]['proposal_state'] == 'saved-without-final-reply'
    original=session_reads._records(tmp_path)['turns'][turn_id]
    version=manuscript_proposals.proposal_version(original)[0]
    selected_view=manuscript_proposals.select_version(original,version)
    assert selected_view['reply']==original['reply'] and selected_view['reply']['status']=='failed'
    assert 'proposal' not in selected_view['reply'] and '_selected_proposal_version' not in original
    selected_view['reply']['status']='caller-local'
    assert original['reply']['status']=='failed'
    writing_records.bank(tmp_path, {'record': 'writing-reply', 'id': 'WR-withdrawn', 'turn_id': turn_id,
        'session_id': session_id, 'project': 'recovery', 'status': 'completed',
        'proposal': {'answer': 'Withdrawn after reconsideration.', 'edits': []}})
    queue=session_reads.pending_proposals(tmp_path,'recovery')
    assert queue['count']==1
    handle=queue['proposals'][0]['read_handle']['native_request']
    selected=writing_tools.call(tmp_path,'recovery','review',handle)['owner_response']
    manuscript_proposals.decide(tmp_path,'recovery',{'project':'recovery','turn_id':turn_id,
        'proposal_version':selected['proposal_version'],'edit_id':selected['edits'][0]['edit_id'],'decision':'reject'})
    assert session_reads.pending_proposals(tmp_path,'recovery')['count']==0
    historical=writing_tools.call(tmp_path,'recovery','review',handle)['owner_response']
    assert historical['edits'][0]['status']=='rejected'
    assert '_selected_proposal_version' not in (tmp_path/'contract/talk.jsonl').read_text()


def test_apply_receipt_does_not_bypass_project_identity(tmp_path):
    _, _, turn_id, _ = prepare(tmp_path)
    version=manuscript_proposals.preview(tmp_path,'recovery',turn_id)['proposal_version']
    with pytest.raises(ValueError, match='another project'):
        source_application.apply_proposal(tmp_path, {'project': 'other', 'turn_id': turn_id,'proposal_version':version})
    source_application.apply_proposal(tmp_path, {'project': 'recovery', 'turn_id': turn_id,'proposal_version':version})
    with pytest.raises(ValueError, match='another project'):
        source_application.apply_proposal(tmp_path, {'project': 'other', 'turn_id': turn_id,'proposal_version':version})
