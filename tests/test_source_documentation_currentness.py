"""Local documentation currentness and the bounded reflexive review (Work5, 2026-10-20), as the existing Work review owner
already provides them: exact per-obligation input pins make a review STALE when one consumed input changes and leave
unrelated accepted scope CURRENT; an independent new review restores only the changed scope.

THE REFLEXIVE CASE, stated exactly. The evaluator is the real, unchanged, accepted review owner
src/laplace/work/project_work_review.py (EVALUATOR_PIN below is its accepted sha256; the test asserts the file that runs IS that
file and lies outside the synthetic candidate root). The fixture's kernel/acceptance.py is an INPUT TEXT the evaluator pins
and judges; it is never imported or executed. Under that unchanged accepted evaluator, a candidate's own acceptance is SELF
and never satisfies, an evaluator pinned outside the candidate satisfies, and the candidate's next edit stales that
acceptance. Actor attestation is identity evidence about who reviewed, not a proof about which program ran; this witness
says nothing about an arbitrarily modified evaluator enforcing rules on itself.

No timestamp, no global ledger freshness, no stored parallel status: everything read here is project_work_review.facet.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from laplace.work import project_work as work, project_work_review as review
from laplace.core.records import journal

P = 'p'
#: the accepted evaluator: src/laplace/work/project_work_review.py at the accepted base ec4afa909 (Sol's unchanged-owner pin); a change
#: to this file is a change to the evaluator and must be re-accepted, which is the reflexive point made concrete
EVALUATOR_PIN = 'sha256:ec8e522c2f7c9cf0526e51e0014f4cd0703f02bb951994f0f22cfab943be5a96'
OBLIGATIONS = [
    {'id': 'code', 'scope': 'source', 'label': 'The module and its page', 'inputs': ['src/a.py', 'docs/a.md']},
    {'id': 'other', 'scope': 'source', 'label': 'An unrelated module', 'inputs': ['src/b.py']},
    {'id': 'acceptance', 'scope': 'source', 'label': 'The acceptance rule itself', 'inputs': ['kernel/acceptance.py']},
]


def sha(root, rel):
    return 'sha256:' + hashlib.sha256((root / rel).read_bytes()).hexdigest()


def turn(root, ident, session, **extra):
    journal.bank_row('contract/talk.jsonl', {'record': 'writing-turn', 'id': ident, 'project': P, 'session_id': session, 'mode': 'work', 'text': 'fixture',
                                             'provider_settings': {'provider': 'codex', 'model': 'fixture-model', 'effort': 'low'}, **extra}, root=root)


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    (tmp_path / 'contract').mkdir()
    (tmp_path / 'registry_projects.json').write_text(json.dumps({'projects': [{'name': P, 'kind': 'general', 'project_dir': 'proj'}]}))
    (tmp_path / 'proj').mkdir()
    for rel, text in (('src/a.py', 'def a():\n    return 1\n'), ('docs/a.md', '# a\n\n`a()` returns 1.\n'), ('src/b.py', 'b = 2\n'),
                      ('kernel/acceptance.py', 'def accepted(review):\n    return review.independent and review.current\n'),
                      ('evidence/evaluator.md', 'The evaluator read the acceptance rule and its tests.\n')):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding='utf-8')
    turn(tmp_path, 'WT-prod', 'WS-prod')                    # the producer (the candidate's own session)
    turn(tmp_path, 'WT-prod-2', 'WS-prod')                  # the producer again, later
    turn(tmp_path, 'WT-rev', 'WS-rev')                      # another session: an independent reviewer
    turn(tmp_path, 'WT-rev-2', 'WS-rev')
    work.task(P, {'id': 'w', 'title': 'Source and documentation', 'goal': 'Keep the page true to the module', 'review_obligations': OBLIGATIONS}, tmp_path)
    return tmp_path


def guard(root):
    return work._task_revision(work._tasks(P, root)['w'])


def record(root, payload, *, turn_id=None, mode='work'):
    door = {'origin': 'native', 'turn_id': turn_id} if turn_id else {'origin': 'human'}
    return review.record(P, {'id': 'w', 'expected_work_revision': guard(root), **payload}, root, door=door, mode=mode)


def facet(root):
    value = review.facet(work._tasks(P, root)['w'], root)
    return {row['id']: row for row in value['obligations']}, value


def handoff(root, request):
    return record(root, {'phase': 'handoff', 'request_id': request, 'obligations': ['code', 'other', 'acceptance'], 'object': {'kind': 'source', 'checkpoint': 'W'},
                         'pins': {rel: sha(root, rel) for rel in ('src/a.py', 'docs/a.md', 'src/b.py', 'kernel/acceptance.py')}}, turn_id='WT-prod')['phase']['id']


def test_a_changed_input_stales_only_its_review_and_an_independent_review_restores_only_that_scope(root):
    hid = handoff(root, 'handoff-first')
    for obligation in ('code', 'other', 'acceptance'):
        record(root, {'phase': 'review', 'request_id': 'review-first-' + obligation, 'handoff_id': hid, 'obligation_id': obligation, 'verdict': 'ACCEPT'}, turn_id='WT-rev', mode='review')
    rows, value = facet(root)
    assert all(rows[o]['status'] == 'ACCEPTED' and rows[o]['currentness'] == 'CURRENT' and rows[o]['independence'] == 'INDEPENDENT' and rows[o]['satisfied'] for o in rows)
    assert value['remaining'] == [] and review.completion_problem(work._tasks(P, root)['w'], root, work._tasks(P, root)) is None
    # source A changes: ONLY its review is stale, with the exact changed input named; B and the acceptance rule stay current
    (root / 'src/a.py').write_text('def a():\n    return 2\n')
    rows, value = facet(root)
    assert rows['code']['currentness'] == 'STALE' and rows['code']['currentness_reason'] == 'Reviewed input changed: src/a.py' and rows['code']['satisfied'] is False
    assert rows['other']['currentness'] == 'CURRENT' and rows['other']['satisfied'] and rows['acceptance']['currentness'] == 'CURRENT'
    assert value['remaining'] == ['code'] and 'remaining: code' in review.completion_problem(work._tasks(P, root)['w'], root, work._tasks(P, root))
    # the page is part of the same scope: bringing the documentation up to the module and reviewing it independently restores ONLY `code`
    (root / 'docs/a.md').write_text('# a\n\n`a()` returns 2.\n')
    hid2 = handoff(root, 'handoff-second')
    record(root, {'phase': 'review', 'request_id': 'review-second-code', 'handoff_id': hid2, 'obligation_id': 'code', 'verdict': 'ACCEPT'}, turn_id='WT-rev-2', mode='review')
    rows, value = facet(root)
    assert rows['code']['currentness'] == 'CURRENT' and rows['code']['satisfied'] and rows['code']['review_id'] != 'review-first-code'
    assert rows['other']['currentness'] == 'CURRENT' and rows['acceptance']['currentness'] == 'CURRENT' and value['remaining'] == []
    # an unrelated change to B stales B alone; A's restored review is untouched
    (root / 'src/b.py').write_text('b = 3\n')
    rows, value = facet(root)
    assert rows['other']['currentness'] == 'STALE' and rows['code']['currentness'] == 'CURRENT' and rows['acceptance']['currentness'] == 'CURRENT' and value['remaining'] == ['other']
    target = os.environ.get('LAPLACE_RECOVERY_EVIDENCE')
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        (Path(target) / 'currentness.json').write_text(json.dumps({o: {k: rows[o].get(k) for k in ('status', 'currentness', 'currentness_reason', 'independence', 'satisfied')} for o in rows}, indent=1))


def evaluator_origin(root) -> dict:
    """The evaluator that actually judges: its file, hash and position outside the candidate root."""
    path = Path(review.__file__).resolve()
    return {'file': str(path), 'sha256': 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest(), 'outside_candidate': not path.is_relative_to(root.resolve()),
            'accepted_pin': EVALUATOR_PIN}


def test_a_change_to_acceptance_code_is_judged_by_the_unchanged_evaluator_outside_the_candidate(root):
    origin = evaluator_origin(root)
    assert origin['outside_candidate'] and origin['file'].endswith('src/laplace/work/project_work_review.py')
    assert origin['sha256'] == EVALUATOR_PIN, 'the evaluator that runs is not the accepted one; re-accept it before trusting this witness'
    hid = handoff(root, 'handoff-first')
    # the candidate's own session "accepts" its acceptance rule: recorded, but SELF, never satisfied
    own = record(root, {'phase': 'review', 'request_id': 'review-self-first', 'handoff_id': hid, 'obligation_id': 'acceptance', 'verdict': 'ACCEPT'}, turn_id='WT-prod-2', mode='review')
    assert own['phase']['independence'] == 'SELF'
    rows, value = facet(root)
    assert rows['acceptance']['status'] == 'ACCEPTED' and rows['acceptance']['independence'] == 'SELF' and rows['acceptance']['satisfied'] is False and 'acceptance' in value['remaining']
    # an evaluator pinned OUTSIDE the candidate (author-attested external identity with public evidence) judges the rule
    evaluator = {'origin': 'external', 'actor': 'accepted-evaluator', 'evidence': [{'path': 'evidence/evaluator.md', 'sha256': sha(root, 'evidence/evaluator.md')}]}
    judged = record(root, {'phase': 'review', 'request_id': 'review-evaluator-1', 'handoff_id': hid, 'obligation_id': 'acceptance', 'verdict': 'ACCEPT', 'actor': evaluator}, mode='review')
    assert judged['phase']['independence'] == 'INDEPENDENT' and judged['phase']['actor']['verified'] is True
    rows, value = facet(root)
    assert rows['acceptance']['satisfied'] is True and rows['acceptance']['reviewer'] == 'accepted-evaluator' and rows['acceptance']['reviewer_verified'] is True
    # the candidate edits the acceptance rule (an input text, never executed): under the UNCHANGED accepted evaluator the pinned
    # acceptance is STALE and the candidate's own re-review is SELF again; only a new independent judgement of the new bytes satisfies
    (root / 'kernel/acceptance.py').write_text('def accepted(review):\n    return True\n')
    rows, value = facet(root)
    assert rows['acceptance']['currentness'] == 'STALE' and rows['acceptance']['satisfied'] is False and rows['acceptance']['currentness_reason'] == 'Reviewed input changed: kernel/acceptance.py'
    hid2 = handoff(root, 'handoff-second')
    again = record(root, {'phase': 'review', 'request_id': 'review-self-second', 'handoff_id': hid2, 'obligation_id': 'acceptance', 'verdict': 'ACCEPT'}, turn_id='WT-prod-2', mode='review')
    rows, value = facet(root)
    assert again['phase']['independence'] == 'SELF' and rows['acceptance']['satisfied'] is False and 'acceptance' in value['remaining']
    # a native turn cannot claim the evaluator's identity by label: the claim is attributed to the claiming session and stays unverified
    claimed = record(root, {'phase': 'review', 'request_id': 'review-claimed-1', 'handoff_id': hid2, 'obligation_id': 'acceptance', 'verdict': 'ACCEPT', 'actor': evaluator}, turn_id='WT-prod-2', mode='review')
    assert claimed['phase']['actor']['verified'] is False and claimed['phase']['independence'] == 'SELF'
    rows, value = facet(root)
    assert rows['acceptance']['satisfied'] is False and rows['acceptance']['reviewer_verified'] is False
    # the completion gate holds the Work open until an independent, current acceptance of the NEW rule exists
    problem = review.completion_problem(work._tasks(P, root)['w'], root, work._tasks(P, root))
    assert problem and 'acceptance' in problem.split('remaining:')[1]
    target = os.environ.get('LAPLACE_RECOVERY_EVIDENCE')
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        (Path(target) / 'reflexive.json').write_text(json.dumps({'evaluator_origin': origin, 'self_review': own['phase']['independence'], 'evaluator': {k: judged['phase'][k] for k in ('independence',)} | {'verified': judged['phase']['actor']['verified'], 'attestation_is': 'identity evidence about the reviewer, not a program-authenticity proof'},
                                                                 'after_candidate_edit': {k: rows['acceptance'].get(k) for k in ('status', 'currentness', 'independence', 'satisfied', 'reviewer_verified')}}, indent=1))
