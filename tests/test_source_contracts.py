"""Source contracts (WORK-source-contract-reflexive-slice-20261021): the follow-up's optional child logical_target through
the real Work owner, and the generic segment/relation resolver over the operation's own declaration.

The BEFORE operation is the base commit's bytes of project_work_review.py (the exact public blob at the pinned base,
retained as an immutable read-only fixture and verified against its pin before use), executed as a
detached module under the owner's module name and never registered in sys.modules; the same declaration rule
(source_contract) is applied to it, so before and after bases come from actual code, not a synthetic edit. Disposable
fixture files only (the lifecycle fixture); no Main, provider or source grant.
"""
from __future__ import annotations

import hashlib
import json
import types
from pathlib import Path

import pytest

from laplace import sdk
from laplace.core import bodies
from laplace.core.identity import canonical_digest
from laplace.native import tools as writing_tools
from laplace.work import development_source, project_work as work, project_work_review as review, source_contracts as sc
from laplace.writing.schemas import SCHEMAS
from test_work_review_lifecycle import P, guard, handoff, native, root, sha  # noqa: F401  (root is the shared fixture)

BASE = 'f3503005323e10baf50e527e61a12c173b197e96'
REPO = Path(__file__).resolve().parents[1]
TARGET = {'kind': 'node', 'node_id': 'concept-guard'}
# The base operation bytes, read once at import (before any fixture arms the repository's test runtime guard): the exact
# public blob of src/laplace/work/project_work_review.py at BASE, retained as a read-only fixture because a check sandbox
# carries no Git history. Its length and pin are verified before the authentic old module is ever executed.
BASE_FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'source_contracts' / (BASE + '-project_work_review.py')
BASE_FIXTURE_SHA256 = 'sha256:d531cbee947628d19d31c3f5090185dc2c8c5ebb0e11d8a5d952a6e43fe466ba'
BASE_BYTES = BASE_FIXTURE.read_bytes()
assert len(BASE_BYTES) == 64039 and 'sha256:' + hashlib.sha256(BASE_BYTES).hexdigest() == BASE_FIXTURE_SHA256, \
    'the fixture must be exactly the blob ' + BASE + ':src/laplace/work/project_work_review.py'


def base_review():
    """The base commit's follow-up owner, detached: same module name (so primitive names match), not imported."""
    source = BASE_BYTES
    module = types.ModuleType('laplace.work.project_work_review')
    module.__dict__['__package__'] = 'laplace.work'
    exec(compile(source, 'base:project_work_review.py', 'exec'), module.__dict__)
    return module


def before_declaration(module):
    return types.FunctionType(review.source_contract.__code__, module.__dict__, 'source_contract')()


def followup(child, request_id='req-follow-T', finding='F1 target', closure='required', root_=None):
    return {'id': 'parent', 'phase': 'followup', 'request_id': request_id, 'expected_work_revision': guard(root_),
            'finding': finding, 'closure': closure, 'child': child}


def test_an_omitted_child_logical_target_keeps_the_base_request_identity_replay_and_recovery(root):
    old = base_review()
    parent = work._tasks(P, root)['parent']
    payload = followup({'title': 'Add the guard', 'goal': 'Refuse stale input'}, root_=root)
    assert review._followup_request(payload, parent, P) == old._followup_request(payload, parent, P), 'same canonical request as the base'
    handoff(root)
    made = native(root, 'WT-rev', payload, mode='review')
    stored = next(row for row in work._tasks(P, root)['parent']['phases'] if row.get('phase') == 'followup')['request']
    assert stored == old._followup_request(payload, parent, P) and 'logical_target' not in stored['child']
    assert 'logical_target' not in work._tasks(P, root)[made['child_id']]
    again = native(root, 'WT-rev', payload, mode='review')
    assert again['status'] == 'REUSED' and again['child_created'] is False


def test_an_explicit_child_logical_target_lands_through_the_task_owner_and_its_drift_refuses(root):
    handoff(root)
    with pytest.raises(ValueError, match='logical_target'):
        native(root, 'WT-rev', followup({'title': 'Bad', 'goal': 'x', 'logical_target': {'kind': 'node', 'path': 'src/a.py'}}, root_=root), mode='review')
    assert not any(row.get('followup_origin') for row in work._tasks(P, root).values()), 'a refused target wrote nothing'
    made = native(root, 'WT-rev', followup({'title': 'Add the guard', 'goal': 'Refuse stale input', 'logical_target': TARGET}, root_=root), mode='review')
    child = made['child_id']
    assert made['status'] == 'JOINED' and work._tasks(P, root)[child]['logical_target'] == TARGET
    # the task owner keeps it as the child's intent (MATERIAL_INTENT), so a later edit is drift for a request that consumed it
    work.task(P, {'id': child, 'expected_work_revision': work._task_revision(work._tasks(P, root)[child]),
                  'logical_target': {'kind': 'node', 'node_id': 'another'}}, root)
    with pytest.raises(work.WorkConflict, match='logical_target changed'):
        native(root, 'WT-rev', followup({'title': 'Add the guard', 'goal': 'Refuse stale input', 'logical_target': TARGET},
                                        request_id='req-follow-T2', root_=root), mode='review')
    # a request that omitted the target keeps its old meaning: the same child is reused without comparing it
    same = native(root, 'WT-rev', followup({'title': 'Add the guard', 'goal': 'Refuse stale input'}, request_id='req-follow-T3', root_=root), mode='review')
    assert same['child_id'] == child and same['child_created'] is False
    assert sum(1 for row in work._tasks(P, root).values() if row.get('followup_origin')) == 1


def test_an_interrupted_join_with_a_child_target_recovers_the_same_request_without_a_duplicate(root, monkeypatch):
    handoff(root)
    real = work._task

    def failing(project, payload, repo_root=None, **kw):
        if payload.get('id') == 'parent':
            raise OSError('disk full')
        return real(project, payload, repo_root, **kw)
    monkeypatch.setattr(work, '_task', failing)
    request = followup({'title': 'Pending', 'goal': 'Join later', 'logical_target': TARGET}, request_id='req-follow-int', root_=root)
    pending = native(root, 'WT-prod', request)
    assert pending['status'] == 'PENDING_JOIN' and work._tasks(P, root)[pending['child_id']]['logical_target'] == TARGET
    issued = pending['review']['pending_joins'][0]['recover']
    assert issued['child'] == {'id': pending['child_id'], 'title': 'Pending', 'goal': 'Join later', 'kind': 'execution',
                               'section_ids': [], 'logical_target': TARGET}, 'the owner issues the exact original request'
    monkeypatch.setattr(work, '_task', real)
    recovered = native(root, 'WT-prod', request)
    assert recovered['status'] == 'RECOVERED' and recovered['child_created'] is False
    assert [row['id'] for row in work._tasks(P, root).values() if row.get('followup_origin')] == [pending['child_id']]
    with pytest.raises(ValueError, match='different follow-up'):
        native(root, 'WT-prod', {**request, 'child': {**request['child'], 'logical_target': {'kind': 'node', 'node_id': 'changed'}}})


def test_the_changed_segments_make_only_their_consumers_pending_and_an_unrelated_operation_stays_current(root):
    before, after = before_declaration(base_review()), review.source_contract()
    accepted = {row['consumer']: sc.accepted_bases(before, row['consumer']) for row in before['relations']}
    judged = sc.standing(after, accepted)
    assert judged['changed_segments'] == ['admission', 'inputs', 'request']
    pending = sorted(name for name, row in judged['consumers'].items() if row['standing'] == 'PENDING_REVIEW')
    current = sorted(name for name, row in judged['consumers'].items() if row['standing'] == 'CURRENT')
    # kernel.declared-source projects every segment of the current declaration, so the changed segments make it pending too.
    assert pending == ['kernel.declared-source', 'native.help.work_review', 'native.work_review', 'tests.work_review_lifecycle.followup',
                       'web.workspace-work-review.phaseRecorder', 'work.project_work_navigation.action_context',
                       'work.project_work_review._followup_effects', 'work.project_work_review._followup_request']
    assert current == ['tests.work_navigation.composition', 'web.workspace-work-review.composition',
                       'work.project_work_review.intent_digest', 'work_review.followup'], 'steps, purpose and the task intent are unchanged'
    # ten obligations of the original consumers plus kernel.declared-source on each of the three changed segments
    assert judged['semantic_currentness'] == 'REVIEW_REQUIRED' and len(judged['obligations']) == 13
    # an independent re-acceptance of one consumer at the new bases repairs only that consumer
    repaired = sc.standing(after, {**accepted, 'native.work_review': sc.accepted_bases(after, 'native.work_review')})
    assert repaired['consumers']['native.work_review']['standing'] == 'CURRENT' and len(repaired['obligations']) == 12
    # the same generic rule over an unrelated operation, and an unknown acceptance is never assumed current
    other = development_source.source_contract()
    unrelated = sc.standing(other, {row['consumer']: sc.accepted_bases(other, row['consumer']) for row in other['relations']})
    assert {row['standing'] for row in unrelated['consumers'].values()} == {'CURRENT'} and unrelated['obligations'] == []
    assert sc.standing(after, {})['consumers']['native.work_review']['standing'] == 'UNREVIEWED'
    # recording a follow-up (receipts, phase rows) changes no segment basis: an observation never stales itself
    bases = sc.bases(after)
    handoff(root)
    native(root, 'WT-rev', followup({'title': 'T', 'goal': 'G', 'logical_target': TARGET}, request_id='req-follow-B', root_=root), mode='review')
    assert sc.bases(review.source_contract()) == bases


def test_the_coarse_contract_descends_to_one_step_or_segment_under_a_budget_and_is_retained_as_bodies():
    coarse = sdk.source_contract('domain.work:work_review.followup')
    assert [row['id'] for row in coarse['steps']] == ['pending', 'child', 'join', 'complete']
    # three projections plus kernel.declared-source, all declared by the current owner
    assert coarse['relations']['projects'] == 4 and coarse['authority'] == review.followup_composition()['authority']
    join = sdk.source_contract('domain.work:work_review.followup', coarse['steps'][2]['next']['select'])
    assert join['item']['primitive'] == 'project_work_review._join' and 'required' in join['item']['closures']
    assert join['recovery'] == review.followup_composition()['recovery'] and join['up'] == {'select': None}
    request = sdk.source_contract('domain.work:work_review.followup', 'segment:request')
    assert 'logical_target' in request['item']['facts']['child'] and {row['consumer'] for row in request['item']['consumers']} >= {'work.project_work_review._followup_request'}
    with pytest.raises(ValueError, match='UNKNOWN_SELECT'):
        sdk.source_contract('domain.work:work_review.followup', 'step:absent')
    with pytest.raises(ValueError, match='BUDGET_EXCEEDED'):
        sdk.source_contract('domain.work:work_review.followup', budget=256)
    # The SDK lists every registered declaration: the four existing ones plus domain.authoring reply_presentation.
    listed = [row['reference']['identity']['operation'] for row in sdk.source_contract()['operations']]
    assert sorted(listed) == sorted(row['operation'] for row in sc.declarations()) and len(listed) == len(sc.providers()) == 5
    assert {'work_review.followup', 'development_source', 'reply_presentation'} <= set(listed)
    store = {}

    def put(raw):
        handle = canonical_digest(raw.decode())
        store[handle] = raw
        return handle
    references = sc.retain(review.source_contract(), put, 'test-bodies')
    assert set(references) == set(review.source_contract()['segments']) and all(bodies.is_reference(row) for row in references.values())


def test_human_native_and_help_consumers_read_the_child_target_from_the_one_declaration(root):
    prepared = review.preparation({}, ['followup'], 'sha256:' + '0' * 64)['phases']['followup']['inputs']
    target = [row for row in prepared if row['path'].startswith('child.logical_target.')]
    assert [(row['path'], row['required']) for row in target] == [('child.logical_target.kind', False), ('child.logical_target.node_id', False)]
    assert SCHEMAS['work_review']['properties']['child']['properties']['logical_target'] == review.CHILD_TARGET
    from laplace.web import project_work_surface as http
    handoff(root)
    status, _, raw = http.handle('/work/review', {}, 'POST', json.dumps({'project': P, **followup(
        {'title': 'Human', 'goal': 'Through the human door', 'logical_target': {'kind': 'node'}}, request_id='req-follow-H', root_=root)}).encode(), repo_root=root)
    assert status == 200, raw   # the human review door's existing success code
    assert work._tasks(P, root)[json.loads(raw)['child_id']]['logical_target'] == {'kind': 'node'}


# ---------------------------------------------------------------------------------------------- the source owner route
# A contained exercise of the REAL development_source owner on a public synthetic checkout. Its root grant goes through
# a SIMULATED human door (project_work_surface.handle called in-process by this test, origin human): it is not an actual
# author/admin grant, and no native actor issues one (refused below). The coordinator performs the actual grant, Source
# API exercise and bounded check separately.
from test_development_source_recipient import _bind, _commit, _human_door, _sha, _task, P as DP, _parent_turn, tree  # noqa: E402,F401

OPERATION = 'src/laplace/work/project_work_review.py'


def declaration_from(raw: bytes):
    module = types.ModuleType('laplace.work.project_work_review')
    module.__dict__['__package__'] = 'laplace.work'
    exec(compile(raw, 'checkout:project_work_review.py', 'exec'), module.__dict__)
    return before_declaration(module)


def test_the_source_owner_applies_the_real_operation_change_recovers_it_and_its_bytes_carry_the_semantic_cone(tree, monkeypatch):
    root = tree
    base = BASE_BYTES
    after = (REPO / OPERATION).read_bytes()
    checkout = root / 'devsrc'
    (checkout / OPERATION).parent.mkdir(parents=True)
    (checkout / OPERATION).write_bytes(base)
    (checkout / 'README.md').write_text('Public synthetic development checkout: one Work operation module at its base commit.\n')
    _commit(checkout, [OPERATION, 'README.md'], b'base operation')
    (root / 'profiles').mkdir(exist_ok=True)
    (root / 'profiles' / 'writing_sources.json').write_text(json.dumps({'repositories': {'devsrc': 'devsrc'}}))
    work.task(DP, {'id': 'dev', 'title': 'Carry the follow-up child target', 'goal': 'Optional child.logical_target through the follow-up',
                   'review_obligations': [{'id': 'source', 'scope': 'source', 'label': 'Source review', 'inputs': ['devsrc/' + OPERATION]}]}, root)
    parent_session, parent_turn = _parent_turn(root)
    binding = _bind(root)
    grant_payload = {'action': 'grant', 'request_id': 'grant-sc-1', 'work_id': 'dev', 'expected_work_revision': work._task_revision(_task(root)),
                     'repository': 'devsrc', 'paths': [OPERATION], 'operations': ['read', 'candidate', 'apply'], 'lifetime_s': 3600,
                     'parent_session_id': parent_session, 'evaluator': binding['id']}
    with pytest.raises(ValueError):   # a native turn never issues its own root grant
        writing_tools.execute(root, DP, 'work', 'development_source', grant_payload, turn_id=parent_turn)
    grant = _human_door(root, '/work/development', grant_payload)['grant']   # SIMULATED human door (labelled above)
    human = {'origin': 'human'}
    read = development_source.read(root, DP, {'action': 'read', 'grant_id': grant['id'], 'path': OPERATION}, human)
    assert read['sha256'] == 'sha256:' + __import__('hashlib').sha256(base).hexdigest()
    with pytest.raises(ValueError, match='preimage'):   # an old source CAS is refused before any candidate is recorded
        development_source.candidate(root, DP, {'action': 'candidate', 'grant_id': grant['id'],
                                                'files': [{'path': OPERATION, 'before_sha256': _sha('stale'), 'content': after.decode()}]}, human)
    with pytest.raises(ValueError):   # outside the granted path scope
        development_source.candidate(root, DP, {'action': 'candidate', 'grant_id': grant['id'],
                                                'files': [{'path': 'README.md', 'before_sha256': read['sha256'], 'content': 'x'}]}, human)
    made = development_source.candidate(root, DP, {'action': 'candidate', 'grant_id': grant['id'],
                                                   'files': [{'path': OPERATION, 'before_sha256': read['sha256'], 'content': after.decode()}]}, human)
    real_append = work._append

    def die_on_publish(root_, row):
        if row.get('kind') == 'development-effect' and row.get('state') != 'PREPARED':
            raise RuntimeError('fixture: interrupted after the write, before the publish row')
        return real_append(root_, row)
    monkeypatch.setattr(work, '_append', die_on_publish)
    with pytest.raises(RuntimeError, match='before the publish row'):
        development_source.apply(root, DP, {'action': 'apply', 'candidate_id': made['candidate_id']}, human)
    monkeypatch.setattr(work, '_append', real_append)
    assert (checkout / OPERATION).read_bytes() == after
    recovered = development_source.apply(root, DP, {'action': 'apply', 'candidate_id': made['candidate_id']}, human)
    effects = [row for row in _task(root)['development'] if row.get('kind') == 'development-effect']
    assert recovered['effect']['state'] == 'COMMITTED' and [row['state'] for row in effects][0] == 'PREPARED'
    assert effects[-1]['actor'] == effects[0]['actor'] and effects[-1]['attempt'] == 2, 'the same request, its original actor'
    assert development_source.apply(root, DP, {'action': 'apply', 'candidate_id': made['candidate_id']}, human)['reused'] is True
    with pytest.raises(ValueError, match='preimage'):   # the base bytes are no longer current: a replay of the old candidate content refuses
        development_source.candidate(root, DP, {'action': 'candidate', 'grant_id': grant['id'],
                                                'files': [{'path': OPERATION, 'before_sha256': read['sha256'], 'content': after.decode()}]}, human)
    # the checkout's own bytes, before and after the source effect, through the same declaration rule
    judged = sc.standing(declaration_from((checkout / OPERATION).read_bytes()),
                         {row['consumer']: sc.accepted_bases(declaration_from(base), row['consumer']) for row in declaration_from(base)['relations']})
    assert judged['changed_segments'] == ['admission', 'inputs', 'request']
    assert sc.bases(declaration_from((checkout / OPERATION).read_bytes())) == sc.bases(review.source_contract()), 'the applied bytes are the executed owner'


# ---------------------------------------------------------------------------------------------- canonical custody and review (SC-R1/SC-R2)
OP = 'domain.work:work_review.followup'


def bound(consumer, operation='work_review.followup', **extra):
    return {'owner': 'domain.work', 'operation': operation, 'consumer': consumer, **extra}


def bound_work(root_, ident, obligations):
    work.task(P, {'id': ident, 'title': 'Bound review', 'goal': 'Review the declared source contract', 'review_obligations': obligations}, root_)


def hand(root_, ident, request_id, obligations, turn='WT-prod', **extra):
    return native(root_, turn, {'id': ident, 'phase': 'handoff', 'request_id': request_id, 'expected_work_revision': guard(root_, ident),
                                'obligations': obligations, **extra})


def verdict(root_, ident, handoff_id, obligation, value, request_id, turn='WT-rev', **extra):
    return native(root_, turn, {'id': ident, 'phase': 'review', 'request_id': request_id, 'expected_work_revision': guard(root_, ident),
                                'handoff_id': handoff_id, 'obligation_id': obligation, 'verdict': value, **extra}, mode='review')


def consumers(root_, operation=OP):
    return sdk.source_contract(operation, root=root_)['standing']['consumers']


def test_a_bound_handoff_publishes_retained_segments_through_the_body_store_and_reads_them_after_reload(root):
    assert 'source_contract' not in work._tasks(P, root)['parent']['review_obligations'][0], 'unbound obligations are unchanged'
    with pytest.raises(ValueError, match='source-scope'):
        bound_work(root, 'sc-guide', [{'id': 'x', 'scope': 'guide', 'label': 'Guide', 'source_contract': bound('native.work_review')}])
    bound_work(root, 'sc-bad', [{'id': 'nobody', 'scope': 'source', 'label': 'N', 'source_contract': bound('nobody')},
                                {'id': 'unconsumed', 'scope': 'source', 'label': 'U', 'source_contract': bound('native.work_review', segments=['steps'])},
                                {'id': 'unsupported', 'scope': 'source', 'label': 'S', 'source_contract': bound('x', operation='not.declared')}])
    for obligation, refusal in (('nobody', 'UNKNOWN_CONSUMER'), ('unconsumed', 'SEGMENT_NOT_CONSUMED'), ('unsupported', 'UNSUPPORTED_OPERATION')):
        with pytest.raises(ValueError, match=refusal):
            hand(root, 'sc-bad', 'req-sc-bad-' + obligation, [obligation])
    assert not work._tasks(P, root)['sc-bad'].get('phases'), 'a refused publication wrote nothing'
    bound_work(root, 'sc', [{'id': 'native', 'scope': 'source', 'label': 'Native payload', 'source_contract': bound('native.work_review')}])
    made = hand(root, 'sc', 'req-sc-hand-1', ['native'])
    held = made['phase']['source_contracts']['native']
    assert set(held['segments']) == {'admission'} and held['version'] == sc.version(review.source_contract())
    assert bodies.is_reference(held['segments']['admission']['body']) and held['segments']['admission']['body']['store'] == 'contract/writing_bodies'
    assert hand(root, 'sc', 'req-sc-hand-1', ['native'])['status'] == 'REUSED'
    with pytest.raises(ValueError, match='different handoff'):
        hand(root, 'sc', 'req-sc-hand-1', ['native'], object={'kind': 'source', 'checkpoint': 'other'})
    work._FOLD_CACHE.clear()   # a reconstructed read: the ledger rows and the body store, nothing held in memory
    retained = sc.read_version(root, 'domain.work', 'work_review.followup', held['version'], select='segment:admission')
    assert retained['state'] == 'RETAINED_VERSION' and retained['item']['facts'] == review.source_contract()['segments']['admission']
    assert retained['not_retained'] == sorted(set(held['bases']) - {'admission'}) and retained['reference']['identity'] == {'operation': 'work_review.followup'}
    assert consumers(root)['native.work_review']['standing'] == 'UNREVIEWED', 'a publication never accepts itself'


def test_only_an_independent_review_of_the_handed_version_is_canonical_acceptance(root):
    bound_work(root, 'sc', [{'id': o, 'scope': 'source', 'label': o, 'source_contract': bound(c)} for o, c in
                            (('native', 'native.work_review'), ('nav', 'work.project_work_navigation.action_context'),
                             ('comp', 'tests.work_navigation.composition'))])
    handoff_id = hand(root, 'sc', 'req-sc-hand-2', ['native', 'nav', 'comp'])['phase']['id']
    with pytest.raises(ValueError):   # a caller cannot inject or renew bases: the review schema has no such field
        verdict(root, 'sc', handoff_id, 'native', 'ACCEPT', 'req-sc-rev-inject', source_contract={'segments': {'admission': 'sha256:' + '0' * 64}})
    accepted = verdict(root, 'sc', handoff_id, 'native', 'ACCEPT', 'req-sc-rev-1')
    assert accepted['phase']['independence'] == 'INDEPENDENT' and accepted['phase']['source_contract']['consumer'] == 'native.work_review'
    verdict(root, 'sc', handoff_id, 'nav', 'ACCEPT', 'req-sc-rev-self', turn='WT-prod-2')        # the producer's own session: SELF
    verdict(root, 'sc', handoff_id, 'comp', 'ACCEPT', 'req-sc-rev-2')
    from laplace.web import project_work_surface as http
    status, _, raw = http.handle('/work/review', {}, 'POST', json.dumps({'project': P, 'id': 'sc', 'phase': 'review', 'request_id': 'req-sc-rev-hold',
        'expected_work_revision': guard(root, 'sc'), 'handoff_id': handoff_id, 'obligation_id': 'comp', 'verdict': 'HOLD',
        'findings': [{'id': 'H1', 'summary': 'Composition text needs a second look'}]}).encode(), repo_root=root)   # the human door
    assert status == 200, raw
    work._FOLD_CACHE.clear()
    standing = consumers(root)
    assert standing['native.work_review']['standing'] == 'CURRENT' and standing['native.work_review']['review']['independence'] == 'INDEPENDENT'
    assert standing['work.project_work_navigation.action_context']['standing'] == 'UNREVIEWED' and 'SELF' in standing['work.project_work_navigation.action_context']['reason']
    assert standing['tests.work_navigation.composition']['standing'] == 'HELD', 'a later HOLD is never covered by the earlier ACCEPT'
    assert standing['native.help.work_review']['standing'] == 'UNREVIEWED'
    # the binding changed after the handoff: the old handoff cannot be reviewed for the new consumer
    task = work._tasks(P, root)['sc']
    changed = [dict(item, source_contract=bound('native.help.work_review')) if item['id'] == 'native' else item for item in task['review_obligations']]
    work.task(P, {'id': 'sc', 'expected_work_revision': guard(root, 'sc'), 'review_obligations': changed}, root)
    with pytest.raises(ValueError, match='binding changed since its handoff'):
        verdict(root, 'sc', handoff_id, 'native', 'ACCEPT', 'req-sc-rev-3')


def test_a_changed_declaration_makes_reviewed_consumers_of_changed_segments_pending_and_a_new_review_repairs_one(root, monkeypatch):
    # the operation as its owner declared it at the base commit (the base bytes under the same declaration rule) is what
    # this first handoff publishes; the registered owner then becomes the head declaration
    before = before_declaration(base_review())
    monkeypatch.setattr(review, 'source_contract', lambda: before)
    obligations = [{'id': o, 'scope': 'source', 'label': o, 'source_contract': bound(c, operation=op)} for o, c, op in
                   (('native', 'native.work_review', 'work_review.followup'), ('nav', 'work.project_work_navigation.action_context', 'work_review.followup'),
                    ('comp', 'tests.work_navigation.composition', 'work_review.followup'), ('dev', 'native.development_source', 'development_source'))]
    bound_work(root, 'sc', obligations)
    first = hand(root, 'sc', 'req-sc-hand-before', ['native', 'nav', 'comp', 'dev'])['phase']
    for index, obligation in enumerate(('native', 'nav', 'comp', 'dev')):
        verdict(root, 'sc', first['id'], obligation, 'ACCEPT', 'req-sc-rev-before-%d' % index)
    monkeypatch.undo()
    old_version = first['source_contracts']['native']['version']
    assert old_version == sc.version(before) != sc.version(review.source_contract())
    snapshot = sdk.source_contract(OP, version=old_version, root=root)
    standing = consumers(root)
    assert standing['native.work_review']['standing'] == 'PENDING_REVIEW' and standing['native.work_review']['changed'] == ['admission']
    assert standing['work.project_work_navigation.action_context']['standing'] == 'PENDING_REVIEW' and standing['work.project_work_navigation.action_context']['changed'] == ['inputs']
    assert standing['tests.work_navigation.composition']['standing'] == 'CURRENT', 'its steps segment is unchanged'
    assert consumers(root, 'domain.work:development_source')['native.development_source']['standing'] == 'CURRENT', 'another operation'
    # repair one consumer: a NEW handoff of the current version and a NEW independent review
    bases = sc.bases(review.source_contract())
    second = hand(root, 'sc', 'req-sc-hand-after', ['native'])['phase']
    verdict(root, 'sc', second['id'], 'native', 'ACCEPT', 'req-sc-rev-after')
    assert sc.bases(review.source_contract()) == bases, 'publishing and reviewing change no basis'
    work._FOLD_CACHE.clear()
    repaired = consumers(root)
    assert repaired['native.work_review']['standing'] == 'CURRENT' and repaired['native.work_review']['review']['version'] == sc.version(review.source_contract())
    assert repaired['work.project_work_navigation.action_context']['standing'] == 'PENDING_REVIEW', 'only the reviewed consumer is repaired'
    assert sdk.source_contract(OP, version=old_version, root=root) == snapshot, 'a retained version never changes'
    assert sorted(sdk.source_contract(OP, root=root)['standing']['versions']) == sorted({old_version, sc.version(review.source_contract())})
    with pytest.raises(ValueError, match='UNKNOWN_VERSION'):
        sdk.source_contract(OP, version='sha256:' + 'f' * 64, root=root)
    reference = sc.reference('domain.work', 'work_review.followup', old_version)
    assert sdk.source_contract(reference=reference, root=root) == snapshot


def test_public_reads_are_detached_from_live_admission_and_record_constants(root):
    bound_work(root, 'sc', [{'id': 'native', 'scope': 'source', 'label': 'N', 'source_contract': bound('native.work_review')}])
    version_ = hand(root, 'sc', 'req-sc-hand-d', ['native'])['phase']['source_contracts']['native']['version']
    live_target, live_kinds, live_bases = json.loads(json.dumps(review.CHILD_TARGET)), dict(development_source.KINDS), sc.bases(review.source_contract())
    current = sdk.source_contract(OP, 'segment:admission', root=root)
    current['item']['facts']['child']['properties']['logical_target']['properties']['kind']['type'] = 'MUTATED'
    sdk.source_contract(OP, root=root)['steps'][0]['id'] = 'MUTATED'
    sdk.source_contract('domain.work:development_source', 'segment:operations', root=root)['item']['facts']['kinds']['grant'] = 'MUTATED'
    review.source_contract()['segments']['admission']['child']['properties']['logical_target']['minProperties'] = 99
    retained = sc.read_version(root, 'domain.work', 'work_review.followup', version_, select='segment:admission')
    retained['item']['facts']['child']['properties']['logical_target']['additionalProperties'] = True
    assert review.CHILD_TARGET == live_target and development_source.KINDS == live_kinds and sc.bases(review.source_contract()) == live_bases
    assert review.contract()['properties']['child']['properties']['logical_target'] == live_target
    assert sc.read_version(root, 'domain.work', 'work_review.followup', version_, select='segment:admission')['item']['facts']['child']['properties']['logical_target'] == live_target
    handoff(root)
    with pytest.raises(ValueError, match='logical_target'):   # native admission still refuses what it refused
        native(root, 'WT-rev', followup({'title': 'T', 'goal': 'G', 'logical_target': {'kind': 'node', 'extra': 'x'}}, request_id='req-follow-D', root_=root), mode='review')


# ---------------------------------------------------------------------------------------------- one admission, one decision, one read (SC-R1a/SC-R1b)
REF = lambda version_=None: sc.reference('domain.work', 'work_review.followup', version_)


def detail(root_, ident):
    from laplace.web import project_work_surface as http
    code, _, raw = http.handle('/work/state', {'project': [P], 'view': ['detail'], 'id': [ident]}, 'GET', repo_root=root_)
    assert code == 200, raw[:300]
    return json.loads(raw)


def discovery_native(root_, request, turn='WT-rev'):
    return writing_tools.execute(root_, P, 'work', 'project', {'view': 'discovery', 'request': request}, turn_id=turn)


def discovery_http(root_, request):
    from laplace.web import project_work_surface as http
    query = {key: [json.dumps(value) if isinstance(value, dict) else str(value)] for key, value in request.items()}
    code, _, raw = http.handle('/work/discovery', query, 'GET', repo_root=root_)
    return code, json.loads(raw)


def test_the_binding_is_admitted_through_the_native_and_human_task_doors_from_the_owner_schema(root):
    # The task schema is oneOf [ordinary task, Work planning]; the ordinary branch composes the binding schema.
    ordinary = next(branch for branch in SCHEMAS['task']['oneOf'] if 'review_obligations' in branch.get('properties', {}))
    assert ordinary['properties']['review_obligations']['items']['properties']['source_contract'] == sc.binding_schema()
    obligations = [{'id': 'native', 'scope': 'source', 'label': 'Native payload', 'source_contract': bound('native.work_review')},
                   {'id': 'future', 'scope': 'source', 'label': 'Authored future intent', 'source_contract': bound('x', operation='not.declared.yet')}]
    made = writing_tools.execute(root, P, 'work', 'task', {'id': 'sc-native', 'title': 'Native bound', 'goal': 'Bound by the native door',
                                                           'review_obligations': obligations}, turn_id='WT-prod')
    assert made and work._tasks(P, root)['sc-native']['review_obligations'][0]['source_contract'] == bound('native.work_review')
    with pytest.raises(ValueError):   # the generated schema refuses an untyped binding at the native door
        writing_tools.execute(root, P, 'work', 'task', {'id': 'sc-bad', 'title': 'B', 'goal': 'G', 'review_obligations': [
            {'id': 'x', 'scope': 'source', 'label': 'X', 'source_contract': {'owner': 'domain.work', 'operation': 'o', 'consumer': 'c', 'path': 'src/a.py'}}]},
            turn_id='WT-prod')
    from laplace.web import project_work_surface as http
    code, _, raw = http.handle('/work/task', {}, 'POST', json.dumps({'project': P, 'id': 'sc-human', 'title': 'Human bound', 'goal': 'Bound by the author',
                                                                     'review_obligations': obligations[:1]}).encode(), repo_root=root)
    assert code == 201, raw
    assert work._tasks(P, root)['sc-human']['review_obligations'][0]['source_contract'] == bound('native.work_review')
    with pytest.raises(ValueError, match='UNSUPPORTED_OPERATION'):   # shape-valid future intent refuses only at its publication
        hand(root, 'sc-native', 'req-sc-future', ['future'])
    assert not work._tasks(P, root)['sc-native'].get('phases')


def test_a_source_only_independent_review_satisfies_the_real_work_and_every_door_agrees(root, monkeypatch):
    bound_work(root, 'sc', [{'id': 'native', 'scope': 'source', 'label': 'Native payload', 'source_contract': bound('native.work_review')}])
    first = hand(root, 'sc', 'req-sc-only-1', ['native'])['phase']
    verdict(root, 'sc', first['id'], 'native', 'ACCEPT', 'req-sc-only-r1')
    row = detail(root, 'sc')['task']['review']['obligations'][0]
    assert (row['satisfied'], row['currentness'], row['source_contract']['consumer']) == (True, 'CURRENT', 'native.work_review')
    assert detail(root, 'sc')['task']['review']['remaining'] == [] and detail(root, 'sc')['task']['review']['next']['kind'] == 'synthesis'
    request = {'facet': 'inspect', 'reference': REF()}
    by_sdk = consumers(root)['native.work_review']
    by_native = discovery_native(root, request)['standing']['consumers']['native.work_review']
    code, by_http = discovery_http(root, request)
    assert code == 200 and by_sdk == by_native == by_http['standing']['consumers']['native.work_review'] and by_sdk['standing'] == 'CURRENT'
    # the owner moves (its admission segment differs): only this consumer's obligation is pending, in every view
    moved_owner = before_declaration(base_review())   # computed before the owner is replaced
    monkeypatch.setattr(review, 'source_contract', lambda: moved_owner)
    row = detail(root, 'sc')['task']['review']['obligations'][0]
    assert (row['satisfied'], row['currentness'], row['changed_segments']) == (False, 'STALE', ['admission'])
    assert detail(root, 'sc')['task']['review']['next'] == {'kind': 'review', 'obligation_id': 'native', 'says': 'Record the source review of "Native payload".'}
    moved = consumers(root)
    assert moved['native.work_review']['standing'] == 'PENDING_REVIEW' and moved['tests.work_navigation.composition']['standing'] == 'UNREVIEWED'
    # a new handoff of the moved declaration and a new independent review repair it, everywhere
    second = hand(root, 'sc', 'req-sc-only-2', ['native'])['phase']
    verdict(root, 'sc', second['id'], 'native', 'ACCEPT', 'req-sc-only-r2')
    work._FOLD_CACHE.clear()
    assert detail(root, 'sc')['task']['review']['obligations'][0]['satisfied'] is True and consumers(root)['native.work_review']['standing'] == 'CURRENT'
    assert review.completion_problem(work._tasks(P, root)['sc'], root, work._tasks(P, root)) is None


def test_a_bound_review_with_explicit_raw_inputs_keeps_those_pins_consumed(root):
    bound_work(root, 'sc', [{'id': 'native', 'scope': 'source', 'label': 'Native payload', 'inputs': ['src/a.py'],
                             'source_contract': bound('native.work_review')}])
    with pytest.raises(ValueError, match='pins every declared input'):
        hand(root, 'sc', 'req-sc-raw-0', ['native'])
    first = hand(root, 'sc', 'req-sc-raw-1', ['native'], pins={'src/a.py': sha(root, 'src/a.py')})['phase']
    verdict(root, 'sc', first['id'], 'native', 'ACCEPT', 'req-sc-raw-r1')
    assert detail(root, 'sc')['task']['review']['obligations'][0]['currentness'] == 'CURRENT' and consumers(root)['native.work_review']['standing'] == 'CURRENT'
    (root / 'src' / 'a.py').write_text('a = 2\n')
    row = detail(root, 'sc')['task']['review']['obligations'][0]
    standing = consumers(root)['native.work_review']
    assert row['currentness'] == 'STALE' and 'src/a.py' in row['currentness_reason'] and row['satisfied'] is False
    assert standing['standing'] == 'PENDING_REVIEW' and standing['reason'] == row['currentness_reason'], 'one decision, every view'
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        verdict(root, 'sc', first['id'], 'native', 'ACCEPT', 'req-sc-raw-r2')
    second = hand(root, 'sc', 'req-sc-raw-2', ['native'], pins={'src/a.py': sha(root, 'src/a.py')})['phase']
    verdict(root, 'sc', second['id'], 'native', 'ACCEPT', 'req-sc-raw-r3')
    assert consumers(root)['native.work_review']['standing'] == 'CURRENT' and detail(root, 'sc')['task']['review']['obligations'][0]['satisfied'] is True


def test_one_normalized_read_refuses_wrong_identity_and_version_and_never_substitutes_current(root, monkeypatch):
    from laplace.core.identity import reference as owner_ref
    from laplace.work import owner_discovery
    refusals = [(owner_ref('core.identity', 'source-contract', {'operation': 'work_review.followup'}), 'WRONG_OWNER'),
                (owner_ref('domain.work', 'source-contract', {'operation': 'work_review.followup', 'project': P}), 'MALFORMED_REFERENCE'),
                (owner_ref('domain.work', 'source-contract', {'operation': 'not.declared'}), 'UNKNOWN_TARGET'),
                (owner_ref('domain.work', 'source-contract', {'operation': 'work_review.followup'}, version={'other': 'x'}), 'UNSUPPORTED_VERSION'),
                (REF(sc.version(review.source_contract())), 'UNKNOWN_VERSION')]   # equal to the current digest, never retained
    for value, code in refusals:
        with pytest.raises(ValueError, match=code):
            sdk.source_contract(reference=value, root=root)
    with pytest.raises(ValueError, match='CONFLICTING_VERSION'):
        sdk.source_contract(reference=REF(), version='sha256:' + '0' * 64, root=root)
    assert sdk.source_contract(reference=REF(), root=root)['state'] == 'CURRENT_DECLARATION', 'current facts stay readable unreviewed'
    bound_work(root, 'sc', [{'id': 'native', 'scope': 'source', 'label': 'N', 'source_contract': bound('native.work_review')}])
    now = hand(root, 'sc', 'req-sc-norm-1', ['native'])['phase']['source_contracts']['native']['version']
    retained = sdk.source_contract(reference=REF(now), root=root)
    assert retained['state'] == 'RETAINED_VERSION' and [row['id'] for row in retained['retained']] == ['admission'], 'explicit current = the retained version'
    moved_owner = before_declaration(base_review())   # computed before the owner is replaced
    monkeypatch.setattr(review, 'source_contract', lambda: moved_owner)
    assert sdk.source_contract(reference=REF(now), root=root) == retained, 'the same reference keeps its meaning after the owner moves'
    other = owner_discovery.request(root, owner_discovery.project_scope('another', 'native'), {'facet': 'inspect', 'reference': REF()})
    assert other['standing']['versions'] == [] and other['standing']['consumers']['native.work_review']['standing'] == 'UNREVIEWED'
    with pytest.raises(ValueError, match='UNKNOWN_VERSION'):   # another namespace's publication is not readable from here
        owner_discovery.request(root, owner_discovery.project_scope('another', 'native'), {'facet': 'inspect', 'reference': REF(now)})


def test_the_whole_envelope_fits_the_budget_and_a_retained_body_is_charged_before_it_is_read(root, monkeypatch):
    from laplace.representation import writing_bodies
    bound_work(root, 'sc', [{'id': 'nav', 'scope': 'source', 'label': 'Nav', 'source_contract': bound('work.project_work_navigation.action_context')}])
    version_ = hand(root, 'sc', 'req-sc-budget-1', ['nav'])['phase']['source_contracts']['nav']['version']
    full = sdk.source_contract(OP, root=root)
    size = len(json.dumps(full, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode())
    with pytest.raises(ValueError, match='BUDGET_EXCEEDED'):   # standing and version history are inside the bound
        sdk.source_contract(OP, root=root, budget=size - 1)
    assert sdk.source_contract(OP, root=root, budget=size) == full
    with pytest.raises(ValueError, match='BUDGET_EXCEEDED'):
        sdk.source_contract(OP, 'segment:admission', root=root, budget=200)
    current = sdk.source_contract(OP, 'segment:inputs', root=root)
    assert current['item']['basis'] == sc.bases(review.source_contract())['inputs']
    reads = []
    real = writing_bodies.read_bytes
    monkeypatch.setattr(writing_bodies, 'read_bytes', lambda value, root_: reads.append(value) or real(value, root_))
    with pytest.raises(ValueError, match='BUDGET_EXCEEDED'):
        sdk.source_contract(OP, 'segment:steps', version=version_, root=root, budget=600)
    assert reads == [], 'refused before the body was read'
    step = sdk.source_contract(OP, 'step:join', version=version_, root=root, budget=sc.MAX_BUDGET)
    assert step['state'] == 'RETAINED_VERSION' and step['item']['primitive'] == 'project_work_review._join' and len(reads) == 1
    segment = sdk.source_contract(OP, 'segment:inputs', version=version_, root=root)
    assert canonical_digest(segment['item']['facts']) == segment['item']['basis'] == current['item']['basis']
    with pytest.raises(ValueError, match='NOT_RETAINED'):
        sdk.source_contract(OP, 'segment:admission', version=version_, root=root)
    with pytest.raises(ValueError, match='BUDGET_EXCEEDED'):
        sdk.source_contract(budget=64)


# ---------------------------------------------------------------------------------------------- qualified independence and coverage
def test_local_non_independent_satisfaction_never_becomes_canonical_independent_acceptance(root):
    bound_work(root, 'sc', [{'id': 'native', 'scope': 'source', 'label': 'Native payload', 'independent': False,
                             'source_contract': bound('native.work_review')}])
    handoff_id = hand(root, 'sc', 'req-sc-ind-1', ['native'])['phase']['id']
    verdict(root, 'sc', handoff_id, 'native', 'ACCEPT', 'req-sc-ind-self', turn='WT-prod-2')   # the producer's own session
    row = detail(root, 'sc')['task']['review']['obligations'][0]
    assert (row['satisfied'], row['independence']) == (True, 'SELF'), 'the Work allows a self review locally'
    standing = consumers(root)['native.work_review']
    assert (standing['standing'], standing['independence'], standing['local_satisfied']) == ('UNREVIEWED', 'SELF', True)
    assert 'not an independent review' in standing['reason'] and 'accepted locally' in standing['reason']
    verdict(root, 'sc', handoff_id, 'native', 'ACCEPT', 'req-sc-ind-indep')
    standing = consumers(root)['native.work_review']
    assert (standing['standing'], standing['independence'], standing['coverage']['missing']) == ('CURRENT', 'INDEPENDENT', [])


def test_a_partial_selected_review_names_its_missing_coverage_and_a_full_review_closes_it(root, monkeypatch):
    bound_work(root, 'sc', [{'id': 'help', 'scope': 'source', 'label': 'Help purpose', 'source_contract': bound('native.help.work_review', segments=['purpose'])}])
    phase = hand(root, 'sc', 'req-sc-cov-1', ['help'])['phase']
    published = phase['source_contracts']['help']
    assert set(published['segments']) == {'purpose'} and set(published['bases']) > {'purpose', 'admission'}, 'all bases identify; one body is handed'
    verdict(root, 'sc', phase['id'], 'help', 'ACCEPT', 'req-sc-cov-r1')
    row = detail(root, 'sc')['task']['review']['obligations'][0]
    assert row['satisfied'] is True and row['coverage'] == {'required': ['admission', 'purpose'], 'covered': ['purpose'], 'missing': ['admission']}
    standing = consumers(root)['native.help.work_review']
    assert (standing['standing'], standing['changed'], standing['coverage']['missing']) == ('UNREVIEWED', [], ['admission'])
    assert len(standing['obligations']) == 1, 'one local coverage obligation, no changed-since-accepted claim'
    moved_owner = before_declaration(base_review())   # the owner's admission moves; the reviewed purpose does not
    monkeypatch.setattr(review, 'source_contract', lambda: moved_owner)
    moved = consumers(root)['native.help.work_review']
    assert (moved['standing'], moved['changed']) == ('UNREVIEWED', []), 'an unreviewed segment cannot have changed since review'
    monkeypatch.undo()
    task = work._tasks(P, root)['sc']
    work.task(P, {'id': 'sc', 'expected_work_revision': guard(root, 'sc'),
                  'review_obligations': [dict(task['review_obligations'][0], source_contract=bound('native.help.work_review'))]}, root)
    full = hand(root, 'sc', 'req-sc-cov-2', ['help'])['phase']
    verdict(root, 'sc', full['id'], 'help', 'ACCEPT', 'req-sc-cov-r2')
    standing = consumers(root)['native.help.work_review']
    assert (standing['standing'], standing['coverage']['missing']) == ('CURRENT', []) and 'obligations' not in standing
    monkeypatch.setattr(review, 'source_contract', lambda: moved_owner)
    assert consumers(root)['native.help.work_review']['changed'] == ['admission'], 'a reviewed segment that moved is a real change'


# ---------------------------------------------------------------------------------------------- domain.authoring reply_presentation
def test_reply_presentation_declares_the_policy_its_code_runs_and_every_shared_consumer():
    from laplace.writing import session_projection as sp
    registered = [provider for provider in sc.providers() if provider.__module__ == 'laplace.writing.session_projection']
    assert registered == [sp.source_contract] and len(sc.providers()) == 5, 'one new provider in the existing registry'
    declared = sc.declaration('domain.authoring', 'reply_presentation')
    assert declared == sp.source_contract() and sc.validate(declared) is declared
    facts = declared['segments']
    assert facts['precedence']['origins'] == list(sp.PRESENTATION_ORIGINS) and facts['inputs']['fields'] == list(sp.PRESENTATION_INPUTS)
    assert facts['fallback']['text'] == sp.STRUCTURED_EDIT_FALLBACK and facts['fallback']['chars'] == 53
    assert facts['nonmutation']['origins_replacing_text'] == list(sp.STRUCTURED_ORIGINS)
    assert facts['currentness']['policy'] == sp.PUBLIC_MESSAGE_PRESENTATION
    row = facts['bounds']['thread_row'];assert (row['shaping_cut_chars'], row['delivered_utf8_bytes']) == (sp.SUMMARY_REPLY_LIMIT, sp.ROW_REPLY_LIMIT)
    assert 'no cut' in facts['bounds']['single_turn_summary'] and 'session_reads.public_message' in facts['bounds']['public_message']
    relations = {row['consumer']: row for row in declared['relations']}
    assert {'kernel.declared-source', 'writing.session_reads.public_message', 'writing.session_projection.turn_summary',
            'writing.tool_sessions.conversation_history', 'writing.turn_context._migration_history'} <= set(relations)
    assert sc.consumed_segments(declared, 'kernel.declared-source') == sorted(facts)
    assert all((REPO / row['location']).is_file() for row in declared['relations']), 'every declared consumer location exists'
    samples = [{'display_text': ''}, {'proposal': {'answer': 'A'}}, {'text': '{"answer":"A","edits":[]}'},
               {'text': '{"edits":[{"file":"a"}]}'}, {'text': 'plain'}, {'error': 'E'}, {'text': '{"edits":[]}'}, {}]
    assert [sp.reply_presentation(reply)['origin'] for reply in samples] == list(sp.PRESENTATION_ORIGINS), 'declared precedence is the executed one'
    coarse = sc.inspect(declared)
    assert coarse['operation'] == 'domain.authoring:reply_presentation' and [row['id'] for row in coarse['steps']] == ['display', 'proposal', 'structured', 'text', 'error']
    assert sc.inspect(declared, 'segment:fallback')['item']['facts']['never'] == ['an empty edits list', 'a structured reply with a usable answer']
    others = {(row['owner'], row['operation']) for row in sc.declarations()} - {('domain.authoring', 'reply_presentation')}
    assert len(others) == 4, 'the four existing declarations remain'
