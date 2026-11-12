"""System runtime/development joined cases (Root 0acf/b4a3, B_runtime_development, 2026-11-02).

Public synthetic owner fixtures join the repaired facts across owners: Writing Stop custody -> Source producer origin ->
Work continuity readiness -> the owner-issued next read or action, and the ONE judge-settlement predicate that the
dispatch continuation offer and its actual admission share. No provider, model, network, private paper or transcript.
These are Source controls only; Root assembled acceptance and actual dogfood remain separate.
"""
import re

import pytest

from test_source_use_joins import source  # noqa: F401  (the public Source fixture)
from test_eigen_continuity_owner import completion, end_producer, summary
from test_eigen_continuity_stop_custody import TURN, bank_request, newer_turn_owns_session, ready_intent
from laplace.work import project_work as W
from laplace.work.project_work_views import handle as view
from laplace.writing import dispatch_execution as E
from test_app_workflow_dispatch import prepared  # noqa: F401  (the public prepared-workflow fixture)
from test_failed_review_continuation import partial  # noqa: F401  (admitted dispatch: completed worker, settled judge)
from laplace.pipeline import workflow_definitions as WD, workflow_operations as OPS
from laplace.writing import workflow_dispatch as F


def test_unknown_stop_custody_is_held_with_exact_codes_and_an_owner_read_never_a_favourable_status(source):
    s = source
    _grant, _account, _candidate, intent = ready_intent(s)
    end_producer(s)   # an ordinary producer end (late proof) never invalidates the Continue
    ready = completion(s, intent)
    assert ready['readiness']['state'] == 'READY' and ready['next']['kind'] == 'continue' and ready['next']['callable']
    before = summary(s)['basis']['token']
    # a genuine Stop request of the producer turn that no host generation binds: never absence, never READY
    bank_request(s, 'public', s['parent']['id'], TURN, None)
    newer_turn_owns_session(s, finish=True)
    held = completion(s, intent)
    assert held['readiness']['state'] == 'HELD'
    step = held['next']
    assert step['kind'] == 'inspect' and step['callable'] is False and step['reason'] == 'HELD'
    assert 'PRODUCER_STOP_UNKNOWN' in step['codes'] and 'no single host generation' in step['detail']
    assert step['read'] == view('public', {'view': 'detail', 'id': 'work'})
    assert 'action' not in step   # nothing callable is offered on unbound Stop evidence
    overview = summary(s)
    assert overview['next']['kind'] == 'inspect' and 'HELD' in overview['next']['reason']
    assert overview['completion']['intents'][0]['readiness']['state'] == 'HELD'
    # an observation taken while READY is not mixed with the held one
    with pytest.raises(W.WorkConflict):
        summary(s, as_of=before)


def test_recorded_hold_review_names_its_disposition_and_the_next_step_addresses_it():
    """A recorded HOLD/REJECT on current bytes is the actual disposition: the review facet names it with its findings and
    exact read, and continuity offers the address step (revised handoff or follow-up), not another paid review. A stale
    ACCEPT keeps the unchanged 'Record the review' step (test_source_contracts pins that exact shape)."""
    from laplace.work import project_work_review as R, project_work_continuity as C
    read = view('public', {'view': 'review', 'id': 'work', 'phase_id': 'PHASE-review-1'})
    held = {'id': 'source', 'scope': 'source', 'label': 'Source change', 'required': True, 'satisfied': False, 'status': 'HOLD',
            'currentness': 'CURRENT', 'currentness_reason': 'Every reviewed pin matches current bytes.', 'review_id': 'PHASE-review-1',
            'findings': 2, 'independence': 'INDEPENDENT', 'review_read': read}
    step = R._next([held], {'id': 'PHASE-handoff-1'}, None, [])
    assert step['kind'] == 'review' and step['obligation_id'] == 'source'
    assert step['disposition']['status'] == 'HOLD' and step['disposition']['review_id'] == 'PHASE-review-1'
    assert step['disposition']['findings'] == 2 and step['disposition']['read'] == read and 'stays binding' in step['says']
    nxt = C._next('public', {'id': 'work'}, {'review': {'next': step}}, [], [])
    assert nxt['kind'] == 'address-review' and nxt['callable'] is False and nxt['read'] == read
    assert nxt['disposition']['status'] == 'HOLD' and 'action' not in nxt   # nothing paid or nudged is manufactured
    rejected = R._next([{**held, 'status': 'REJECTED'}], {'id': 'PHASE-handoff-1'}, None, [])
    assert C._next('public', {'id': 'work'}, {'review': {'next': rejected}}, [], [])['kind'] == 'address-review'
    moved = R._next([{**held, 'currentness': 'STALE', 'currentness_reason': 'Reviewed input changed: src/a.py'}], {'id': 'PHASE-handoff-1'}, None, [])
    assert moved['disposition']['currentness'] == 'STALE' and moved['says'].endswith('Record the source review of "Source change".')
    stale_accept = R._next([{**held, 'status': 'ACCEPTED', 'currentness': 'STALE'}], {'id': 'PHASE-handoff-1'}, None, [])
    assert stale_accept == {'kind': 'review', 'obligation_id': 'source', 'says': 'Record the source review of "Source change".'}
    fresh = R._next([{**held, 'review_id': None, 'status': 'AWAITING_REVIEW', 'currentness': 'UNKNOWN'}], {'id': 'PHASE-handoff-1'}, None, [])
    assert fresh == {'kind': 'review', 'obligation_id': 'source', 'says': 'Record the source review of "Source change".'}


def test_source_candidate_contract_declares_the_exact_preimage_pin_its_validator_compares(tmp_path):
    """A's typed-action need: files[].before_sha256 declares the exact lexical pin the candidate validator compares (what
    read returns: sha256:<64 lowercase hex> of the whole current file) or null for a new file, so a bare digest is refused
    by the declared contract itself instead of surfacing first as a pin mismatch. No validator or authority is relaxed."""
    from jsonschema import Draft202012Validator
    from laplace.work import development_source as Dev
    schema = Dev.contract()
    target = tmp_path / 'file.txt'
    target.write_text('public bytes\n', encoding='utf-8')
    pin = Dev._pin(target)
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', pin) and Dev._pin(tmp_path / 'absent.txt') is None

    def errors(value):
        return list(Draft202012Validator(schema).iter_errors({'action': 'candidate', 'grant_id': 'DG-public', 'files': [
            {'path': 'file.txt', 'before_sha256': value, 'content': 'x'}]}))
    assert not errors(pin) and not errors(None)
    for spelling in (pin.removeprefix('sha256:'), 'sha256:' + pin.removeprefix('sha256:').upper(), 'sha256:' + '0' * 63, 'md5:' + '0' * 32, ''):
        assert errors(spelling), spelling
    declared = schema['properties']['files']['items']['properties']['before_sha256']
    assert declared is Dev.PREIMAGE_PIN and 'read returns' in declared['description'] and 'null' in declared['description']


def test_summary_next_names_a_current_hold_before_superseded_history_and_keeps_live_codes():
    """Review PHASE-0f221e76 F3/F6: a superseded intent is permanent history and never masks the review disposition;
    a live HELD intent is still named, with its exact reason codes rather than prose only."""
    from laplace.work import project_work_continuity as C
    read = view('public', {'view': 'review', 'id': 'work', 'phase_id': 'PHASE-review-1'})
    disposition = {'review_id': 'PHASE-review-1', 'status': 'HOLD', 'currentness': 'CURRENT', 'findings': 1, 'read': read}
    superseded = ({'id': 'CI-' + '1' * 24}, {'state': 'CLOSED', 'reasons': [
        {'code': 'SUPERSEDED', 'successor': 'CI-' + '2' * 24, 'reason': 'The producer armed a superseding intent.'}]})
    continued = ({'id': 'CI-' + '2' * 24}, {'state': 'CONTINUED', 'reasons': []})
    held_review = {'review': {'next': {'kind': 'review', 'obligation_id': 'source', 'disposition': disposition,
                                       'says': 'Review PHASE-review-1 recorded HOLD with 1 finding(s).'}}}
    nxt = C._next('public', {'id': 'work'}, held_review, [superseded, continued], [])
    assert nxt['kind'] == 'address-review' and nxt['read'] == read and nxt['disposition']['status'] == 'HOLD'
    plain = C._next('public', {'id': 'work'}, {'review': {}}, [superseded, continued], [])
    assert plain['kind'] == 'inspect' and 'CI-' + '1' * 24 not in plain['reason']
    held = ({'id': 'CI-' + '3' * 24}, {'state': 'HELD', 'reasons': [{'code': 'PRODUCER_STOP_UNKNOWN', 'reason': 'Stop custody unknown.'}]})
    named = C._next('public', {'id': 'work'}, {'review': {}}, [superseded, held], [])
    assert named['intent_id'] == held[0]['id'] and named['codes'] == ['PRODUCER_STOP_UNKNOWN'] and named['state'] == 'HELD'


def test_session_family_versions_resolve_current_or_retained_and_contradictions_refuse(source):
    """Root e331: ONE canonical record-family rule in records._index. A legitimate same-ID writing-session upsert is a
    version (current by default, an exact retained row on request); a turn whose session has two versions still reads;
    an immutable-identity contradiction, a cross-project session ID and an immutable duplicate refuse."""
    from laplace.writing import records
    from laplace.writing.records import _index as I
    root = source['root']
    base = {'record': 'writing-session', 'id': 'WS-family-public', 'project': 'public', 'role': 'review',
            'provider': 'codex', 'model': 'fixture-model', 'effort': 'low'}
    records.bank(root, base)
    records.bank(root, {**base, 'effort': 'high'})   # a legitimate settings upsert of the same session
    records.bank(root, {'record': 'writing-turn', 'id': 'WT-family-public', 'session_id': base['id'], 'project': 'public', 'mode': 'review'})
    idx = records.index(root)
    current = I.resolve_record_family(idx, 'public', base['id'])
    assert current['version']['family'] == 'writing-session' and current['version']['selection'] == 'current'
    assert current['raw']['effort'] == 'high' and current['version']['versions_total'] == 2 and current['version']['is_current']
    rows = sorted(idx.by_id[base['id']], key=lambda row: row['_order'])
    retained = I.resolve_record_family(idx, 'public', base['id'], retained_row_sha256=rows[0]['_hash'])
    assert retained['raw']['effort'] == 'low' and retained['version']['selection'] == 'retained' and not retained['version']['is_current']
    assert retained['version']['current_row_sha256'] == rows[-1]['_hash'] != retained['version']['selected_row_sha256']
    with pytest.raises(ValueError, match='changed since discovery'):
        I.resolve_record_family(idx, 'public', base['id'], expected_row_sha256=rows[0]['_hash'])
    with pytest.raises(ValueError, match='name only one'):
        I.resolve_record_family(idx, 'public', base['id'], expected_row_sha256=rows[-1]['_hash'], retained_row_sha256=rows[0]['_hash'])
    with pytest.raises(I.AmbiguousRecord):
        I.resolve_record_family(idx, 'public', base['id'], kind='writing-turn')
    assert I.resolve_record_family(idx, 'other', base['id']) is None   # another project sees no row
    turn = I.resolve_record_family(idx, 'public', 'WT-family-public')
    assert turn['version']['family'] == 'writing-turn' and turn['version']['supporting_row_sha256'] == [
        {'record': 'writing-session', 'id': base['id'], 'row_sha256': rows[-1]['_hash']}]
    # the B consumers compose the same rule
    assert records.selected_journal_fields('public', 'WT-family-public', root, fields=['mode'])['mode'] == 'review'
    assert records.selected_journal_fields('public', base['id'], root, fields=['effort'])['effort'] == 'high'
    view = I._snapshot(records.index(root), None)   # the cut snapshot applies the same rule: current version, no issue
    assert view.sessions[base['id']]['_hash'] == rows[-1]['_hash']
    assert not [issue for issue in view.identity_issues if issue['id'] == base['id']]
    # a cross-project session ID is a collision, not a version
    foreign = {**base, 'id': 'WS-family-collision'}
    records.bank(root, foreign)
    records.bank(root, {**foreign, 'project': 'other'})
    with pytest.raises(I.AmbiguousRecord, match='another record kind or project'):
        I.resolve_record_family(records.index(root), 'public', foreign['id'])
    # an immutable-identity contradiction is a refusal, never the latest row
    records.bank(root, {**base, 'role': 'author'})
    with pytest.raises(I.AmbiguousRecord, match='immutable role'):
        I.resolve_record_family(records.index(root), 'public', base['id'])
    with pytest.raises(ValueError, match='ambiguous'):
        records.selected_journal_fields('public', base['id'], root, fields=['effort'])


def test_review_contract_publishes_the_limits_its_recorder_enforces():
    """A's peer friction (handoff summary 2000, object.checkpoint 200, evidence sha256: prefix): the owner contract and
    phase schema carry the SAME constants the recording validators enforce, so a preflight or declaration derived from
    the factory refuses before a paid call. No bound is widened."""
    from jsonschema import Draft202012Validator
    from laplace.work import project_work_review as R
    schema = R.phase_schema('handoff')
    base = {'id': 'WORK-public', 'phase': 'handoff', 'request_id': 'handoff-request-1', 'expected_work_revision': 'sha256:' + '0' * 64}

    def errors(**over):
        return list(Draft202012Validator(schema).iter_errors({**base, **over}))
    assert not errors(summary='s' * R.MAX_TEXT, object={'checkpoint': 'c' * R.MAX_OBJECT_TEXT},
                      evidence=[{'path': 'docs/public.md', 'sha256': 'sha256:' + 'a' * 64}])
    assert errors(summary='s' * (R.MAX_TEXT + 1))
    assert errors(object={'checkpoint': 'c' * (R.MAX_OBJECT_TEXT + 1)})
    assert errors(evidence=[{'path': 'docs/public.md', 'sha256': 'a' * 64}])
    assert errors(actor={'role': 'r' * (R.MAX_ROLE_TEXT + 1)})
    assert R.LIMITS['object_field'] == R.MAX_OBJECT_TEXT and R.LIMITS['summary'] == R.MAX_TEXT and R.LIMITS['sha256'] == '^sha256:[0-9a-f]{64}$'
    with pytest.raises(ValueError, match='at most %d' % R.MAX_OBJECT_TEXT):
        R._text('c' * (R.MAX_OBJECT_TEXT + 1), 'object checkpoint', limit=R.MAX_OBJECT_TEXT)


def test_workflow_handles_issue_one_canonical_url_for_equal_references():
    """The app-run uses/river reads (and every owner handle) issue one HTTP URI per meaning: a reference loaded from a
    pin and one built by the factory differ only in key order, never in the issued read."""
    first = WD.handle('WDEF-' + '0' * 32, 'sha256:' + '1' * 64, facet='uses', reference={'b': 1, 'a': {'d': 2, 'c': 3}})
    second = WD.handle('WDEF-' + '0' * 32, 'sha256:' + '1' * 64, facet='uses', reference={'a': {'c': 3, 'd': 2}, 'b': 1})
    assert first['http']['url'] == second['http']['url'] and first['request'] == second['request']
    assert first['native'] == second['native']


def test_session_creation_identity_refuses_two_creations_and_keeps_upserts_and_legacy_versions(tmp_path):
    """Root ruling ART-9e1c3774 on the operator counterexample: two writing-session rows that both record a different
    created_at are two creations (refuse); a normal creation then admission/configuration upsert retains created_at
    (current version resolves); a legacy version without created_at stays admissible. Settings are never identity."""
    from laplace.writing import records
    from laplace.writing.records import _index as I
    root = tmp_path
    base = {'record': 'writing-session', 'project': 'public', 'role': 'author', 'provider': 'claude', 'model': 'opus', 'effort': 'high'}
    for created in (1.0, 2.0):   # the operator's exact counterexample
        records.bank(root, {**base, 'id': 'WS-same', 'created_at': created})
    with pytest.raises(I.AmbiguousRecord, match='creation identity'):
        I.resolve_record_family(records.index(root), 'public', 'WS-same', kind='writing-session')
    records.bank(root, {**base, 'id': 'WS-kept', 'created_at': 5.0})
    records.bank(root, {**base, 'id': 'WS-kept', 'created_at': 5.0, 'effort': 'low'})   # the upsert restates created_at
    kept = I.resolve_record_family(records.index(root), 'public', 'WS-kept', kind='writing-session')
    assert kept['raw']['effort'] == 'low' and kept['version']['versions_total'] == 2 and kept['version']['selection'] == 'current'
    records.bank(root, {**base, 'id': 'WS-legacy'})                                   # legacy creation row without created_at
    records.bank(root, {**base, 'id': 'WS-legacy', 'created_at': 7.0, 'effort': 'low'})
    legacy = I.resolve_record_family(records.index(root), 'public', 'WS-legacy')
    assert legacy['raw']['effort'] == 'low' and legacy['version']['versions_total'] == 2


J = 'WT-judge'


@pytest.mark.parametrize('execution,settled', [
    ({'turn_id': J, 'state': 'FINISHED'}, True),
    ({'turn_id': J, 'state': 'FAILED'}, True),
    ({'turn_id': J, 'state': 'CANCELLED'}, True),
    ({'turn_id': J, 'state': 'BLOCKED', 'dependency_state': 'BLOCKED', 'finished_at': 1.0, 'result_status': 'failed'}, True),
    ({'turn_id': J, 'state': 'BLOCKED', 'dependency_state': 'BLOCKED'}, False),   # no terminal record: its host may still run
    ({'turn_id': J, 'state': 'BLOCKED', 'dependency_state': 'WAITING', 'finished_at': 1.0}, False),
    ({'turn_id': J, 'state': 'BLOCKED', 'dependency_state': 'BLOCKED', 'finished_at': 1.0, 'provider_inference_started': True}, False),
    ({'turn_id': J, 'state': 'BLOCKED', 'dependency_state': 'BLOCKED', 'finished_at': 1.0, 'provider_process': {'pid': 1}}, False),
    ({'turn_id': J, 'state': 'FINISHED', 'active_provider_processes': [{'pid': 1}]}, False),
    ({'turn_id': J, 'state': 'FINISHED', 'active_auxiliary_processes': [{'pid': 1}]}, False),
    ({'turn_id': J, 'state': 'RUNNING'}, False),
    ({'turn_id': J, 'state': 'WAITING'}, False),
    ({'turn_id': J, 'state': 'ORPHANED'}, False),
    ({'turn_id': J, 'state': 'UNKNOWN-OWNERSHIP'}, False),
    ({'turn_id': 'WT-another-turn', 'state': 'FINISHED'}, False),
    ({}, False)])
def test_one_judge_settlement_predicate_serves_offer_and_actual_admission(execution, settled):
    assert (E.settled_judge_problem(execution, J) is None) is settled


def test_app_run_maps_parent_synthesis_observation_reads_reply_identity_and_cancel_to_existing_owners(prepared, partial):
    """C consumes these app-run fields once: authored synthesis is the ORIGINAL parent's state/read (not an unselected
    step), the existing same-scope uses/river reads are issued on the run and list, each child names its public reply
    read identity, and the guarded Cancel dispatched work is the same owner action the parent continuation offers."""
    root, caller = prepared[0], prepared[1]
    _root, ident, plan, _worker = partial
    task = W._tasks('book', root)[ident]
    reference = task['prepared_workflow']['reference']
    row = WD._select(WD._rows(root), caller, {'reference': reference})[0]
    run = F.run(root, caller, row, task)
    synthesis = run['parent_synthesis']
    assert synthesis['execution_location'] == 'original-parent'
    assert synthesis['parent_session_id'] == run['parent']['prepared_by']['session_id']
    assert synthesis['launched_by_turn_id'] == 'prepare-turn' and synthesis['return_path'] == plan['synthesis_return_path']
    assert synthesis['status'] == 'MISSING' and synthesis['consumed'] == run['carrier']['parent_contract']['authored_synthesis_consumed']
    reads = run['observation_reads']
    assert reads['river'] == WD.scoped_handle(caller, facet='river', reference=reference, work_id=ident)
    assert reads['uses'] == WD.scoped_handle(caller, facet='uses', reference=reference)
    cancel = run['actions']['cancel_dispatch']
    assert cancel['payload']['id'] == ident and cancel['payload']['status'] == 'cancelled' and cancel['payload']['project'] == 'book'
    assert 'selected-turn Stop' in cancel['distinct_from'] and 'terminates no provider' in cancel['cancellation_meaning']
    judge = next(step for step in run['steps'] if step['packet'] == plan['packets'][1]['packet'])
    identity = judge['public_reply_read']['identity']
    assert {key: identity.get(key) for key in ('project', 'session_id', 'turn_id', 'part')} == {
        'project': 'book', 'session_id': 'WS-child-1', 'turn_id': 'WT-child-1', 'part': 'reply'}
    listed = F.read(root, caller, row, {'facet': 'app-runs'})
    assert listed['uses_read'] == reads['uses'] and listed['items'][0]['river_read'] == reads['river']
    river = OPS.read(root, caller, {'facet': 'river', 'reference': reference, 'work_id': ident})
    assert any(item['name'] == 'cancel_dispatch' for item in river['actions'])
    assert all('reply' in item.get('reads', {}) for item in river['items'] if item.get('turn_id'))


def _family_session(**over):
    return {'record': 'writing-session', 'project': 'public', 'role': 'author', 'provider': 'claude', 'model': 'opus',
            'effort': 'high', **over}


def _snapshot_basis(view):
    return ({key: row['_hash'] for key, row in view.sessions.items()}, {key: row['_hash'] for key, row in view.turns.items()},
            sorted((issue['kind'], issue['id'], issue['status']) for issue in view.identity_issues))


def test_one_cut_bounded_identity_rule_keeps_an_earlier_snapshot_after_later_collisions(tmp_path):
    """B HOLD PHASE-c7e728 F1: every collision/duplicate/creation check of a cut snapshot sees only rows inside its cut.
    A same-ID session row of another project and a same-ID row of another kind appended AFTER the cut leave the earlier
    snapshot unchanged; the current snapshot and the live resolver detect both; a cut-bound view resolves as of its cut."""
    from laplace.writing import records
    from laplace.writing.records import _index as I
    root = tmp_path
    records.bank(root, _family_session(id='WS-cut', created_at=5))
    records.bank(root, {'record': 'writing-turn', 'id': 'WT-cut', 'session_id': 'WS-cut', 'project': 'public', 'mode': 'work'})
    idx = records.index(root)
    cut = idx.order
    earlier = I._snapshot(idx, cut)
    basis = _snapshot_basis(earlier)
    assert 'WS-cut' in earlier.sessions and 'WT-cut' in earlier.turns and not earlier.identity_issues
    records.bank(root, _family_session(id='WS-cut', created_at=5, project='other'))     # later foreign-project session row
    records.bank(root, {'record': 'writing-steer', 'id': 'WT-cut', 'project': 'public', 'turn_id': 'WT-cut'})  # later other kind
    idx = records.index(root)
    assert idx.order > cut
    again = I._snapshot(idx, cut)
    assert _snapshot_basis(again) == basis and _snapshot_basis(earlier) == basis
    current = I._snapshot(idx, None)
    flagged = {(issue['kind'], issue['id']) for issue in current.identity_issues}
    assert {('writing-session', 'WS-cut'), ('writing-turn', 'WT-cut')} <= flagged
    assert 'WS-cut' not in current.sessions and 'WT-cut' not in current.turns
    as_of = I.resolve_record_family(again, 'public', 'WT-cut')   # the same rule on the cut-bound view
    assert as_of['version']['supporting_row_sha256'][0]['id'] == 'WS-cut'
    assert I.resolve_record_family(again, 'public', 'WS-cut')['version']['versions_total'] == 1
    for ident in ('WS-cut', 'WT-cut'):
        with pytest.raises(I.AmbiguousRecord):
            I.resolve_record_family(idx, 'public', ident)


def test_snapshot_single_row_and_resolver_share_one_declared_identity_scope(tmp_path):
    """B HOLD F2: (b) a single-row session that collides with another project's row of another kind is a snapshot issue
    exactly as the resolver refuses it; (c) a session-claimed ID refuses from EVERY side; (a) duplicate rows of one
    immutable turn ID are two rows in the snapshot as in the resolver; an immutable ID in two projects is each project's
    own identity (the declared project scope), and a later duplicate inside one project refuses only there."""
    from laplace.writing import records
    from laplace.writing.records import _index as I
    root = tmp_path
    records.bank(root, _family_session(id='WS-single'))
    records.bank(root, {'record': 'writing-turn', 'id': 'WS-single', 'project': 'other', 'session_id': 'WS-elsewhere'})
    idx = records.index(root)
    view = I._snapshot(idx, None)
    issues = {(issue['kind'], issue['id']) for issue in view.identity_issues}
    assert 'WS-single' not in view.sessions and ('writing-session', 'WS-single') in issues
    assert 'WS-single' not in view.turns and ('writing-turn', 'WS-single') in issues
    for project in ('public', 'other'):
        with pytest.raises(I.AmbiguousRecord, match='another record kind or project'):
            I.resolve_record_family(idx, project, 'WS-single')
    records.bank(root, _family_session(id='WS-ok'))
    turn = {'record': 'writing-turn', 'id': 'WT-twice', 'project': 'public', 'session_id': 'WS-ok', 'mode': 'work'}
    records.bank(root, turn)
    records.bank(root, turn)
    idx = records.index(root)
    assert len(idx.by_id['WT-twice']) == 2
    view = I._snapshot(idx, None)
    assert 'WT-twice' not in view.turns and ('writing-turn', 'WT-twice') in {(i['kind'], i['id']) for i in view.identity_issues}
    with pytest.raises(I.AmbiguousRecord, match='immutable writing-turn ID has 2 rows'):
        I.resolve_record_family(idx, 'public', 'WT-twice')
    for project in ('public', 'other'):
        records.bank(root, {'record': 'writing-artifact', 'id': 'ART-shared', 'project': project,
                            'path': 'notes/%s.md' % project, 'scope': 'project', 'sha256': '0' * 64})
    idx = records.index(root)
    assert I.resolve_record_family(idx, 'public', 'ART-shared')['raw']['path'] == 'notes/public.md'
    assert I.resolve_record_family(idx, 'other', 'ART-shared')['raw']['path'] == 'notes/other.md'
    assert I.artifact_record(root, 'public', 'ART-shared')['path'] == 'notes/public.md'
    records.bank(root, {'record': 'writing-artifact', 'id': 'ART-shared', 'project': 'public',
                        'path': 'notes/again.md', 'scope': 'project', 'sha256': '1' * 64})
    with pytest.raises(I.AmbiguousRecord):
        I.artifact_record(root, 'public', 'ART-shared')
    with pytest.raises(I.AmbiguousRecord, match='immutable writing-artifact ID has 2 rows'):
        I.resolve_record_family(records.index(root), 'public', 'ART-shared')
    assert I.resolve_record_family(records.index(root), 'other', 'ART-shared')['raw']['path'] == 'notes/other.md'


def test_numeric_creation_identity_is_one_creation_and_unlike_text_is_not_coerced(tmp_path):
    """B HOLD F3: created_at 5 and 5.0 are one creation (a legitimate upsert resolves, in the resolver and the snapshot);
    5 and '5' or 1 and True are two creations (refuse), since no authored rule coerces text or bool into a number."""
    from laplace.writing import records
    from laplace.writing.records import _index as I
    root = tmp_path
    records.bank(root, _family_session(id='WS-number', created_at=5))
    records.bank(root, _family_session(id='WS-number', created_at=5.0, effort='low'))
    kept = I.resolve_record_family(records.index(root), 'public', 'WS-number')
    assert kept['raw']['effort'] == 'low' and kept['version']['versions_total'] == 2 and kept['version']['is_current']
    for ident, first, second in (('WS-text', 5, '5'), ('WS-bool', 1, True), ('WS-other', 5, 6)):
        records.bank(root, _family_session(id=ident, created_at=first))
        records.bank(root, _family_session(id=ident, created_at=second, effort='low'))
        with pytest.raises(I.AmbiguousRecord, match='creation identity'):
            I.resolve_record_family(records.index(root), 'public', ident)
    view = I._snapshot(records.index(root), None)
    issues = {issue['id'] for issue in view.identity_issues}
    assert view.sessions['WS-number']['_hash'] == kept['version']['current_row_sha256'] and 'WS-number' not in issues
    assert {'WS-text', 'WS-bool', 'WS-other'} <= issues and not {'WS-text', 'WS-bool', 'WS-other'} & set(view.sessions)


def _dispatch_journal(root):
    """The exact received dispatch journal (Root novel_dispatch_predicates.py): one worker session and turn of DIS."""
    from laplace.writing import records
    session = {'record': 'writing-session', 'id': 'WS', 'project': 'p', 'role': 'worker', 'dispatch_id': 'DIS', 'packet': 'P1', 'created_at': 1}
    turn = {'record': 'writing-turn', 'id': 'WT', 'session_id': 'WS', 'project': 'p', 'mode': 'work', 'dispatch_id': 'DIS'}
    for row in (session, turn):
        records.bank(root, row)
    return session, turn


@pytest.mark.parametrize('case', ['foreign-session', 'session-other-kind', 'turn-other-kind', 'duplicate-reply'])
def test_dispatch_fold_refuses_every_identity_the_canonical_resolver_refuses(tmp_path, case):
    """Root identity review R1 (novel-dispatch-results.json): before the repair each received collision was refused by the
    canonical resolver yet admitted by the selected dispatch fold, which projected the duplicate reply as 'completed'.
    The captured cut now keeps the colliding rows as identity evidence and every consumed reply is resolved."""
    from laplace.writing import records
    from laplace.writing.records import _index as I, _fold
    session, _turn = _dispatch_journal(tmp_path)
    if case == 'foreign-session':
        records.bank(tmp_path, {**session, 'project': 'q'})
    elif case == 'session-other-kind':
        records.bank(tmp_path, {'record': 'writing-steer', 'id': 'WS', 'project': 'p'})
    elif case == 'turn-other-kind':
        records.bank(tmp_path, {'record': 'writing-steer', 'id': 'WT', 'project': 'p'})
    else:
        for status in ('failed', 'completed'):
            records.bank(tmp_path, {'record': 'writing-reply', 'id': 'WR', 'project': 'p', 'session_id': 'WS', 'turn_id': 'WT', 'status': status})
    key = {'duplicate-reply': 'WR', 'turn-other-kind': 'WT'}.get(case, 'WS')
    with pytest.raises(I.AmbiguousRecord):
        I.resolve_record_family(records.index(tmp_path), 'p', key)
    with pytest.raises(ValueError, match='identity is ambiguous'):
        _fold._dispatch_records(tmp_path, 'p', 'DIS')


def test_dispatch_fold_keeps_lawful_session_versions_and_another_projects_own_reply_identity(tmp_path):
    """The positive side of R1: a legitimate later session version of the same identity, another project's own immutable
    reply under the same ID (lawful for the canonical resolver too) and this turn's one reply remain admissible; the fold
    projects the current session version and this project's settled reply, never the foreign row."""
    from laplace.writing import records
    from laplace.writing.records import _index as I, _fold
    session, _turn = _dispatch_journal(tmp_path)
    records.bank(tmp_path, {**session, 'provider': 'codex', 'effort': 'low'})
    records.bank(tmp_path, {'record': 'writing-reply', 'id': 'WR', 'project': 'p', 'session_id': 'WS', 'turn_id': 'WT', 'status': 'completed'})
    records.bank(tmp_path, {'record': 'writing-reply', 'id': 'WR', 'project': 'q', 'session_id': 'WS-q', 'turn_id': 'WT-q', 'status': 'failed'})
    assert I.resolve_record_family(records.index(tmp_path), 'p', 'WR')['raw']['status'] == 'completed'
    state, _lookup = _fold._dispatch_records(tmp_path, 'p', 'DIS')
    assert (state['turns']['WT'].get('reply') or {}).get('status') == 'completed'
    assert state['sessions']['WS']['effort'] == 'low' and state['sessions']['WS']['role'] == 'worker'


def _source_turn(root):
    """The exact received Source journal (Root novel_predicates.py): one attached author turn with its admission."""
    from laplace.writing import records, source_execution as X
    policy = {'commission_request_id': 'public-proof-identity', 'max_admitted_native_invocations': 20, 'max_app_admissions': 3,
              'max_sessions': 2, 'wall_seconds': 3600}
    attached = X.descriptor('p', 'WORK', 'DG', 'WS', policy)
    session = {'record': 'writing-session', 'id': 'WS', 'project': 'p', 'role': 'author', 'created_at': 1}
    turn = {'record': 'writing-turn', 'id': 'WT', 'session_id': 'WS', 'project': 'p', 'source_execution': attached, 'source_admission_id': 'SA'}
    admission = {'record': 'writing-source-admission', 'id': 'SA', 'project': 'p', 'commission_id': attached['commission_id'],
                 'allowance_revision': attached['allowance_revision'], 'session_id': 'WS', 'new_session': False}
    for row in (session, admission, turn):
        records.bank(root, row)
    assert X.for_turn(root, 'p', 'WT') == attached
    return attached, session, turn


@pytest.mark.parametrize('case', ['duplicate-turn', 'contradictory-session', 'duplicate-reply'])
def test_source_producer_authority_refuses_ambiguous_canonical_provenance(tmp_path, case):
    """Root identity review R2: the canonical resolver refused each received case while Source still trusted the latest-row
    maps (for_turn kept the attachment; producer_origin projected terminal 'completed', no Stop). Source authority now
    resolves its turn, supporting session and every terminal reply through the same rule, so readiness holds instead."""
    from laplace.writing import records, source_execution as X
    from laplace.writing.records import _index as I
    _attached, session, turn = _source_turn(tmp_path)
    if case == 'duplicate-turn':
        records.bank(tmp_path, turn)
        key, kind = 'WT', 'writing-turn'
    elif case == 'contradictory-session':
        records.bank(tmp_path, {**session, 'role': 'review'})
        key, kind = 'WS', 'writing-session'
    else:
        for status in ('interrupted', 'completed'):
            records.bank(tmp_path, {'record': 'writing-reply', 'id': 'WR', 'project': 'p', 'session_id': 'WS', 'turn_id': 'WT', 'status': status})
        key, kind = 'WR', 'writing-reply'
    with pytest.raises(I.AmbiguousRecord):
        I.resolve_record_family(records.index(tmp_path), 'p', key, kind=kind)
    if case != 'duplicate-reply':
        with pytest.raises(X.AllowanceRefused, match='ambiguous'):
            X.for_turn(tmp_path, 'p', 'WT')
    with pytest.raises(X.AllowanceRefused, match='ambiguous'):
        X.producer_origin(tmp_path, 'p', 'WT')


def test_source_producer_authority_keeps_lawful_versions_and_unattached_legacy_turns(tmp_path):
    """The positive side of R2: a legitimate later session version keeps the attachment and one settled reply is the
    terminal state; an ambiguous legacy turn that no row attaches to Source keeps its unbound owner-specific admission."""
    from laplace.writing import records, source_execution as X
    attached, session, _turn = _source_turn(tmp_path)
    records.bank(tmp_path, {**session, 'provider': 'claude', 'effort': 'high'})
    records.bank(tmp_path, {'record': 'writing-reply', 'id': 'WR', 'project': 'p', 'session_id': 'WS', 'turn_id': 'WT', 'status': 'completed'})
    assert X.for_turn(tmp_path, 'p', 'WT') == attached
    origin = X.producer_origin(tmp_path, 'p', 'WT')
    assert origin['terminal'] == 'completed' and origin['stop_requested'] is False and origin['stop_custody']['state'] == 'NONE'
    legacy = {'record': 'writing-turn', 'id': 'WT-legacy', 'session_id': 'WS', 'project': 'p'}
    records.bank(tmp_path, legacy)
    records.bank(tmp_path, legacy)
    assert X.for_turn(tmp_path, 'p', 'WT-legacy') is None
    with pytest.raises(X.AllowanceRefused, match='turn unavailable'):
        X.for_turn(tmp_path, 'other', 'WT')   # a turn only another project holds stays refused


def test_delivery_origin_custody_uses_the_canonical_family_for_lawful_versions_and_foreign_ids(tmp_path):
    """Root app2: work_delivery._source_origin pre-checked custody with the latest-row index.turns map, so a lawful current
    turn was refused when another project holds its own immutable WT (that foreign row is the latest). It now resolves the
    turn through THE canonical family rule that for_turn uses: a real multi-version session with a settings update and
    another project's own ID pass custody and reach the Source attachment; a session mismatch, a turn only another
    project holds and an immutable duplicate refuse before any delivery effect."""
    from laplace.writing import records
    from laplace.work import work_delivery as WD
    _attached, session, _turn = _source_turn(tmp_path)
    records.bank(tmp_path, {**session, 'provider': 'codex', 'effort': 'low', 'settings_revision': 'r2'})   # lawful later version
    records.bank(tmp_path, {'record': 'writing-session-settings', 'id': 'WSS-lawful-1', 'session_id': 'WS', 'project': 'p', 'effort': 'high'})
    records.bank(tmp_path, {'record': 'writing-turn', 'id': 'WT', 'session_id': 'WS-q', 'project': 'q'})   # project q's own WT, banked last
    # custody passes; the attached Source turn then needs its qualified basis, the NEXT owner rule (not custody)
    with pytest.raises(ValueError, match='requires its qualified Source basis'):
        WD._source_origin(tmp_path, 'p', {'turn_id': 'WT', 'session_id': 'WS'}, None, None)
    plain = {'record': 'writing-turn', 'id': 'WT-plain', 'session_id': 'WS', 'project': 'p'}
    records.bank(tmp_path, plain)
    assert WD._source_origin(tmp_path, 'p', {'turn_id': 'WT-plain', 'session_id': 'WS'}, None, None) is None   # unattached, lawful
    for project, actor in (('p', {'turn_id': 'WT-plain', 'session_id': 'WS-other'}), ('other', {'turn_id': 'WT-plain'})):
        with pytest.raises(ValueError, match='custody is unavailable or changed'):
            WD._source_origin(tmp_path, project, actor, None, None)
    records.bank(tmp_path, plain)   # an immutable duplicate is ambiguous custody, never a latest-row answer
    with pytest.raises(ValueError, match='custody is ambiguous'):
        WD._source_origin(tmp_path, 'p', {'turn_id': 'WT-plain', 'session_id': 'WS'}, None, None)


def _foreign_twin(root):
    """Project q's OWN globally identified session WS-q and its own immutable turn under the same ID WT (lawful)."""
    from laplace.writing import records
    root.mkdir(parents=True, exist_ok=True)
    records.bank(root, {'record': 'writing-session', 'id': 'WS-q', 'project': 'q', 'role': 'author', 'created_at': 2})
    records.bank(root, {'record': 'writing-turn', 'id': 'WT', 'session_id': 'WS-q', 'project': 'q'})


def _completed_reply(root):
    from laplace.writing import records
    records.bank(root, {'record': 'writing-reply', 'id': 'WR', 'project': 'p', 'session_id': 'WS', 'turn_id': 'WT', 'status': 'completed'})


@pytest.mark.parametrize('order', ['foreign-first', 'selected-first'])
def test_reply_supporting_turn_resolves_in_its_own_project_beside_another_projects_same_id(tmp_path, order):
    """Root N1 (corrective review report b6a59069): _supporting_rows resolved a reply's immutable supporting turn across
    projects, so project q's own lawful session WS-q and turn WT made p's completed reply WR ambiguous ('2 rows across 2
    projects'), refusing in producer_origin (readiness HELD) and in the dispatch fold. The supporting turn now resolves in
    the selected project first; in BOTH row orders producer_origin reports completed, the dispatch fold projects
    completed and the reply's supporting trace names p's own turn row."""
    from laplace.writing import records, source_execution as X
    from laplace.writing.records import _index as I, _fold
    src, disp = tmp_path / 'source', tmp_path / 'dispatch'
    for root in (src, disp):
        root.mkdir(parents=True, exist_ok=True)
        if order == 'foreign-first':
            _foreign_twin(root)
    _source_turn(src)
    _dispatch_journal(disp)
    for root in (src, disp):
        if order == 'selected-first':
            _foreign_twin(root)
        _completed_reply(root)
    origin = X.producer_origin(src, 'p', 'WT')
    assert origin['terminal'] == 'completed' and origin['stop_requested'] is False
    state, _lookup = _fold._dispatch_records(disp, 'p', 'DIS')
    assert (state['turns']['WT'].get('reply') or {}).get('status') == 'completed' and state['sessions']['WS']['role'] == 'worker'
    idx = records.index(src)
    reply, turn = I.resolve_record_family(idx, 'p', 'WR'), I.resolve_record_family(idx, 'p', 'WT', kind='writing-turn')
    assert {'record': 'writing-turn', 'id': 'WT', 'row_sha256': turn['meta']['_hash']} in reply['version']['supporting_row_sha256']
    assert I.resolve_record_family(idx, 'q', 'WT', kind='writing-turn')['raw']['session_id'] == 'WS-q'   # q keeps its own identity


@pytest.mark.parametrize('case', ['duplicate-reply', 'kind-collision', 'session-collision'])
def test_reply_supporting_turn_scope_keeps_every_genuine_ambiguity_refused(tmp_path, case):
    """The adverse side of N1, each beside project q's lawful same-ID turn: a duplicate p reply, a same-project kind
    collision on WT and a global collision of p's session WS still refuse in producer_origin and in the dispatch fold."""
    from laplace.writing import records, source_execution as X
    from laplace.writing.records import _fold
    src, disp = tmp_path / 'source', tmp_path / 'dispatch'
    for root in (src, disp):
        _foreign_twin(root)
    _attached, session, _turn = _source_turn(src)
    dispatch_session, _dispatch_turn = _dispatch_journal(disp)
    for root, own in ((src, session), (disp, dispatch_session)):
        _completed_reply(root)
        if case == 'duplicate-reply':
            _completed_reply(root)
        elif case == 'kind-collision':
            records.bank(root, {'record': 'writing-steer', 'id': 'WT', 'project': 'p'})
        else:
            records.bank(root, {**own, 'project': 'q'})
    with pytest.raises(X.AllowanceRefused, match='ambiguous'):
        X.producer_origin(src, 'p', 'WT')
    with pytest.raises(ValueError, match='identity is ambiguous'):
        _fold._dispatch_records(disp, 'p', 'DIS')


def test_reply_supporting_original_held_only_by_another_project_stays_refused(tmp_path):
    """N1 keeps the foreign-only refusal: when the selected project holds no row of the supporting turn ID, it is still read
    across projects and the foreign original is refused, never adopted as p's supporting identity."""
    from laplace.writing import records
    from laplace.writing.records import _index as I
    _foreign_twin(tmp_path)
    records.bank(tmp_path, {'record': 'writing-reply', 'id': 'WR-p', 'project': 'p', 'session_id': 'WS-q', 'turn_id': 'WT', 'status': 'completed'})
    with pytest.raises(ValueError, match='another project'):
        I.resolve_record_family(records.index(tmp_path), 'p', 'WR-p')
