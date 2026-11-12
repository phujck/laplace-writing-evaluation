"""CI-E1: the accepted common contract through the REAL inner application writer, at the native and HTTP doors.

No adjudicator, feedback, editor-save or effect owner is replaced. The recipe is the recovery test's: a synthetic
project, context and session; one turn that consults the real derived document view (its PDF) and banks a literal
two-edit proposal through the real propose_revision tool; no provider turn. The PDF is then removed. Edit one is
applied through the native proposal decision, edit two through HTTP POST /authoring/proposal-decision, and replays
of both make no second effect. The checkout the HTTP door serves is chosen through its real resolver
(LAPLACE_REPO_ROOT); provider processes and network connections are refused for the whole case.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

from laplace.web import authoring as authoring_surface
from laplace.manuscript import manuscript_proposals as proposals
from laplace.projects import library as writing_projects
from laplace.native import tools as writing_tools
from laplace.pipeline import authoring
from laplace.core.identity import bytes_digest as digest
from laplace.projects import artifacts
from laplace.writing.records._bank import bank
from laplace.writing.records._fold import _CACHE
from laplace.writing.turn_admission import new_session
from laplace.writing.turn_jobs import _JOBS

SOURCE = '\\documentclass{article}\n\\begin{document}\nOriginal prose.\n\nSecond paragraph.\n\\end{document}\n'
PROVIDERS = {'claude', 'codex', 'gemini', 'openai', 'anthropic', 'ollama'}


@pytest.fixture(autouse=True)
def contained(tmp_path, monkeypatch):
    """The served checkout is this fixture; provider processes and network connections are refused."""
    monkeypatch.setenv('LAPLACE_REPO_ROOT', str(tmp_path))
    spawned = []
    popen = subprocess.Popen.__init__

    def guarded(self, args, *rest, **kwargs):
        argv = [args] if isinstance(args, (str, bytes, os.PathLike)) else list(args)
        name = os.path.basename(str(argv[0]).split()[0]) if argv else ''
        spawned.append(name)
        if name in PROVIDERS:
            raise PermissionError('provider process refused in the effect witness: %s' % name)
        return popen(self, args, *rest, **kwargs)

    def refuse(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise PermissionError('network refused in the effect witness')
        return connect(self, address)

    connect = socket.socket.connect
    monkeypatch.setattr(subprocess.Popen, '__init__', guarded)
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    _CACHE.clear()
    _JOBS.clear()
    yield spawned
    _CACHE.clear()
    _JOBS.clear()
    assert not PROVIDERS & set(spawned)


def prepare(root: Path, *, evidence: bool = False, first_after: str = 'Revised prose.'):
    source = root / 'source'
    source.mkdir(parents=True)
    file = source / 'Book.tex'
    file.write_text(SOURCE)
    code, value = writing_projects.import_source({'name': 'witness', 'title': 'Witness', 'root': 'source/Book.tex', 'editable': True}, root)
    assert code == 201, value
    context = authoring.build_context('witness', {'files': ['Book.tex']}, root)
    session = new_session(root, 'witness', 'codex', 'not-invoked', 'low')
    turn = 'WT-witness'
    bank(root, {'record': 'writing-turn', 'id': turn, 'session_id': session['id'], 'project': 'witness',
                            'request_id': 'witness-request', 'text': 'Revise both paragraphs.', 'mode': 'work',
                            'selection': {'files': ['Book.tex']}, 'context_id': context['context_id'],
                            'dependencies': context['dependencies'], 'document': context['document'], 'consumed': context['consumed']})
    (source / 'Book.pdf').write_bytes(b'%PDF-1.4 synthetic derived output\n')
    seen = writing_tools.execute(root, 'witness', 'work', 'document', {}, turn_id=turn)
    assert seen.get('pdf_identity') and seen.get('ok', True), sorted(seen)
    if evidence:
        (artifacts.project_root(root, 'witness') / 'claim-evidence.txt').write_text('Original controlled evidence.')
        read = writing_tools.execute(root, 'witness', 'work', 'read_artifact', {'path': 'claim-evidence.txt', 'scope': 'project'}, turn_id=turn)
        assert 'Original controlled evidence.' in json.dumps(read), read
    proposed = {'answer': 'Two independent paragraph revisions.', 'edits': [
        {'file': 'Book.tex', 'line_start': 3, 'line_end': 3, 'before': 'Original prose.', 'after': first_after, 'reason': 'First.'},
        {'file': 'Book.tex', 'line_start': 5, 'line_end': 5, 'before': 'Second paragraph.', 'after': 'Revised second.', 'reason': 'Second.'}]}
    sealed = writing_tools.execute(root, 'witness', 'work', 'propose_revision', proposed, turn_id=turn)
    assert sealed['ok'], sealed
    (source / 'Book.pdf').unlink()   # the consulted derived output the source repair will regenerate is now absent
    preview = proposals.preview(root, 'witness', turn)
    return file, turn, preview


def rows(root, record):
    return [row for row in map(json.loads, (root / 'contract/talk.jsonl').read_text().splitlines()) if row['record'] == record]


def feedback(file):
    path = file.parent / 'feedback/feedback.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def native(root, turn, payload):
    return writing_tools.request(root, 'witness', 'revise', {'verb': 'delete', 'concept': 'proposal@paragraph', 'target': '',
                                                            'expected': [], 'payload': payload, 'by': ''}, turn_id=turn)


def http(payload):
    status, _, body = authoring_surface.handle('/authoring/proposal-decision', {}, 'POST', json.dumps({'project': 'witness', **payload}).encode())
    return status, json.loads(body)


def selector(turn, preview, index):
    return {'turn_id': turn, 'proposal_version': preview['proposal_version'], 'edit_id': preview['edits'][index]['edit_id'], 'decision': 'accept'}


def test_real_writer_applies_each_edit_once_through_native_and_http_with_one_typed_pending_review(tmp_path):
    file, turn, preview = prepare(tmp_path)
    assert not (file.parent / 'Book.pdf').exists()
    first = native(tmp_path, turn, selector(turn, preview, 0))
    assert first['ok'] and first['outcome'] == 'applied', first
    reply = first['owner_response']
    application = reply['application']
    assert application['complete'] and application['result_grade'] == 'APPLIED_REVIEW_PENDING'
    [obligation] = reply['review_obligations']
    assert reply['review_obligation_count'] == 1 and obligation['schema'] == 'laplace.scoped-obligation/1'
    assert obligation['kind'] == 'CONSULTED_INPUT_CHANGED' and obligation['detail'] == {'operation': 'document'}
    # The real writer changed exactly the first paragraph and left the independent neighbour.
    assert file.read_text() == SOURCE.replace('Original prose.', 'Revised prose.')
    stored = rows(tmp_path, 'writing-application')
    assert len(stored) == 1 and stored[0]['id'] == application['id'] and stored[0]['review_obligations'] == [obligation]
    assert stored[0]['receipts'][0]['version_id'] and stored[0]['candidate_version'] == preview['proposal_version']
    [owned] = stored[0]['owned_changes']['files']   # the owned-effect receipt the real writer observed
    assert stored[0]['owned_changes']['schema_version'] == 'laplace.owner-mutation/1' and owned['path'] == 'source/Book.tex'
    assert owned['before_sha256'] == digest(SOURCE.encode()) and owned['after_sha256'] == owned['observed_after_sha256'] == digest(file.read_bytes())
    [note] = feedback(file)
    assert (note['kind'], note['by'], note['anchor']['before'], note['anchor']['after']) == (
        'author-rewrite', 'author:accepted-model', 'Original prose.', 'Revised prose.')
    after_first = file.read_bytes()
    # Replays through either door make no second effect.
    replay = native(tmp_path, turn, selector(turn, preview, 0))
    assert not replay['ok'] or (replay['owner_response'].get('application') or {}).get('id') in (None, application['id'])
    status, again = http(selector(turn, preview, 0))
    assert status >= 400 or (again.get('application') or {}).get('id') in (None, application['id']), again
    assert file.read_bytes() == after_first and len(rows(tmp_path, 'writing-application')) == 1 and len(feedback(file)) == 1
    # The independent neighbour applies through HTTP and carries the same one obligation.
    status, second = http(selector(turn, preview, 1))
    assert status == 200, second
    assert second['application']['result_grade'] == 'APPLIED_REVIEW_PENDING'
    assert [row['id'] for row in second['application']['review_obligations']] == [obligation['id']]
    assert file.read_text() == SOURCE.replace('Original prose.', 'Revised prose.').replace('Second paragraph.', 'Revised second.')
    assert len(rows(tmp_path, 'writing-application')) == 2 and len(feedback(file)) == 2
    _CACHE.clear()
    status, third = http(selector(turn, preview, 1))
    assert status >= 400 or (third.get('application') or {}).get('id') in (None, second['application']['id']), third
    assert len(rows(tmp_path, 'writing-application')) == 2 and len(feedback(file)) == 2


@pytest.mark.parametrize('door', ['native', 'http'])
def test_real_writer_refuses_a_wrong_current_source_at_each_door(tmp_path, door):
    file, turn, preview = prepare(tmp_path)
    file.write_text(SOURCE.replace('Original prose.', 'A concurrent author edit.'))
    before = file.read_bytes()
    if door == 'native':
        refused = native(tmp_path, turn, selector(turn, preview, 0))
        assert not refused['ok'] and refused['refused']['said'], refused
    else:
        status, body = http(selector(turn, preview, 0))
        assert status >= 400, body
    assert file.read_bytes() == before and not rows(tmp_path, 'writing-application') and not feedback(file)


@pytest.mark.parametrize('door', ['native', 'http'])
def test_real_writer_refuses_changed_consumed_evidence_at_each_door(tmp_path, door):
    file, turn, preview = prepare(tmp_path, evidence=True)
    (artifacts.project_root(tmp_path, 'witness') / 'claim-evidence.txt').write_text('Changed experimental conclusion.')
    if door == 'native':
        refused = native(tmp_path, turn, selector(turn, preview, 0))
        assert not refused['ok'] and refused['refused']['said'], refused
    else:
        status, body = http(selector(turn, preview, 0))
        assert status >= 400 and 'read_artifact' in json.dumps(body), body
    assert file.read_text() == SOURCE and not rows(tmp_path, 'writing-application') and not feedback(file)


def test_real_writer_reads_a_large_retained_proposal_body_back_through_the_captured_index(tmp_path):
    """The banked proposal is larger than Writing's custody floor, so its row carries a body reference; applying it
    through the real native decision must read that body back (core.bodies under Writing's policy) and write its
    exact text."""
    from laplace.core import bodies as core_bodies
    large = ' '.join('Revised prose sentence %d with \\emph{care} — 雪.' % n for n in range(260))
    file, turn, preview = prepare(tmp_path, first_after=large)
    from laplace.representation import writing_bodies as bodies
    [banked] = rows(tmp_path, 'writing-proposal')
    reference = banked['proposal']
    assert core_bodies.is_reference(reference) and reference['store'] == bodies.STORE and reference['bytes'] > 8192
    body = bodies.read_bytes(reference, tmp_path)
    assert len(body) == reference['bytes'] and json.loads(body)['edits'][0]['after'] == large
    [action] = [row for row in rows(tmp_path, 'writing-tool-action') if row.get('operation') == 'propose_revision']
    leaf = bodies.resolve_fields(action, tmp_path, strict=True)   # the request's large text is its own leaf body
    assert leaf['payload']['edits'][0]['after'] == large and core_bodies.is_reference(action['payload'])
    inner = json.loads(bodies.read_bytes(action['payload'], tmp_path))
    assert core_bodies.is_reference(inner['edits'][0]['after']) and inner['edits'][0]['after']['bytes'] == len(core_bodies.encode(large))
    with core_bodies.budget() as ledger:
        first = native(tmp_path, turn, selector(turn, preview, 0))
    assert first['ok'] and first['outcome'] == 'applied', first
    assert ledger['reads'] >= 1 and ledger['read_bytes'] >= reference['bytes']
    assert file.read_text() == SOURCE.replace('Original prose.', large)
    [note] = feedback(file)
    assert note['anchor']['after'] == large
    replay = native(tmp_path, turn, selector(turn, preview, 0))
    assert not replay['ok'] or (replay['owner_response'].get('application') or {}).get('id') == first['owner_response']['application']['id']
    assert len(rows(tmp_path, 'writing-application')) == 1 and len(feedback(file)) == 1

