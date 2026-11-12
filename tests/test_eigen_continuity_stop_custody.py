"""Durable selected-turn Stop custody (Root4b22, A378d F5; corrected after review PHASE-c9e54875 F1-F5).

The Writing selected-turn Stop owner banks ONE exact project/session/turn/host-generation Stop request in the existing
talk journal before it reports success; source_execution.producer_origin reads it, read-only, beside the volatile shared
marker and the local job flag. Both sides take the generation from turn_control.recorded_generation. A Stop binds its
recorded host generation; a missing, foreign or ambiguous generation gains no authority. Public synthetic session/turn
rows exercise the real owners: no provider, model, process or network runs here.
"""
import json

import pytest

from test_source_use_joins import source  # noqa: F401  (the public Source fixture)
from test_eigen_continuity_owner import HUMAN, PRODUCER, arm_payload, completion, produce, proof, work
from laplace.work import development_source as D, project_work as W, project_work_continuity as C
from laplace.writing import child_hosts, records, source_execution as X, turn_control, turn_jobs

TURN = 'WT-allowance'
NEWER = 'WT-newer-turn'
FOREIGN_HOST = {'pid': 1, 'created_at': 'another-generation'}
THIRD_HOST = {'pid': 2, 'created_at': 'third-generation'}
DTO = {'interrupted': True, 'turn_ids': [TURN]}


def ready_intent(s):
    grant, account, candidate = produce(s)
    intent = D.handle(s['root'], 'public', arm_payload(s, grant, candidate), PRODUCER)['intent']
    _saved, reference = proof(s)
    D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'a-functional', 'reference': reference}, HUMAN)
    assert completion(s, intent)['readiness']['state'] == 'READY'
    return grant, account, candidate, intent


def remote_running(s, host=None, turn=TURN):
    """The remote-controller branch (no in-process job): a turn's execution row with a host birth identity."""
    turn_jobs._JOBS.pop(turn, None)
    child_hosts._begin_child_execution(s['root'], s['parent']['id'], {
        'state': 'RUNNING', 'turn_id': turn, 'project': 'public', 'host': host or child_hosts._process_identity(),
        'provider_inference_started': True, 'remote_steering': True})


def marker(s):
    return child_hosts._host_path(s['root'], s['parent']['id']).with_suffix('.cancel.json')


def newer_turn_owns_session(s, finish=False):
    """A newer turn of the same session replaces the shared execution row and marker (with finish, also the finished record)."""
    remote_running(s, turn=NEWER)
    child_hosts._write_host(marker(s), {'turn_id': NEWER, 'requested_at': 9.0})
    if finish:
        child_hosts._finish_child_execution(s['root'], s['parent']['id'], NEWER, 'completed')


def stop(s, **over):
    return turn_control.interrupt_turn(s['root'], {'project': 'public', 'turn_id': TURN, **over})


def stop_rows(s):
    lines = (s['root'] / 'contract/talk.jsonl').read_text(encoding='utf-8').splitlines()
    return [row for row in map(json.loads, filter(str.strip, lines)) if row.get('record') == turn_control.STOP_REQUEST]


def generation(s):
    return turn_control.recorded_generation(s['root'], s['parent']['id'], TURN)


def origin(s):
    return X.producer_origin(s['root'], 'public', TURN)


def bank_request(s, project, session, turn, value, **over):
    records.bank(s['root'], {'record': turn_control.STOP_REQUEST, 'id': turn_control.stop_request_id(project, session, turn, value),
                             'project': project, 'session_id': session, 'turn_id': turn, 'execution_generation': value,
                             'state': 'REQUESTED', 'scope': 'selected-turn', 'ts': '2026-10-30T00:00:00+00:00', **over})


def test_exact_stop_stays_binding_after_a_completed_race_and_a_newer_turn_replacing_the_row(source):
    """A's original F5 sequence on the real owners: a pure read observes CLOSED and appends nothing; a legitimate
    completed reply then races the Stop and a newer turn replaces the shared marker, then the shared execution row,
    then also the finished record (review F1). CLOSED must hold throughout."""
    s = source
    _grant, _account, _candidate, intent = ready_intent(s)
    remote_running(s)
    assert stop(s) == DTO   # the Stop DTO is unchanged
    assert child_hosts._read_host(marker(s))['turn_id'] == TURN
    here = generation(s)
    [fact] = stop_rows(s)
    # review F4: the write side banked the generation the read side's single function reports
    assert here and fact['id'] == turn_control.stop_request_id('public', s['parent']['id'], TURN, here)
    assert {key: fact[key] for key in ('project', 'session_id', 'turn_id', 'execution_generation', 'state', 'scope')} == {
        'project': 'public', 'session_id': s['parent']['id'], 'turn_id': TURN, 'execution_generation': here,
        'state': 'REQUESTED', 'scope': 'selected-turn'}
    assert not {'commission_id', 'allowance_revision', 'claim_id'} & set(fact)
    # a recorded request is not a stopped process: the remotely steered provider still runs until it consumes the Stop
    assert child_hosts.child_execution(s['root'], s['parent']['id'])['state'] == 'RUNNING'
    ledger = W._ledger(s['root'])
    before = ledger.read_bytes()
    assert completion(s, intent)['readiness']['state'] == 'CLOSED'
    assert completion(s, intent)['readiness']['state'] == 'CLOSED' and ledger.read_bytes() == before
    # Real Stop can race a naturally completed provider result; the actual Stop fact must remain binding.
    records.bank(s['root'], {'record': 'writing-reply', 'id': 'WR-public-natural-completion-race', 'turn_id': TURN,
                             'session_id': s['parent']['id'], 'project': 'public', 'status': 'completed',
                             'text': 'Controlled natural completion crossed the observed Stop, no model.'})
    child_hosts._finish_child_execution(s['root'], s['parent']['id'], TURN, 'completed')
    child_hosts._write_host(marker(s), {'turn_id': NEWER, 'requested_at': 2.0})
    observed = origin(s)
    assert observed['terminal'] == 'completed' and observed['stop_marker'] is None
    assert observed['stop_requested'] is True and observed['stop_request']['id'] == fact['id']
    later = completion(s, intent)['readiness']
    assert later['state'] == 'CLOSED', 'Observed exact Stop must not regain READY after a natural completed result and later-turn marker replacement'
    assert 'PRODUCER_STOPPED' in [row['code'] for row in later['reasons']] and later['facts']['producer_stopped'] is True
    # review F1: a newer turn owns the shared execution row (its finished record still names TURN), then finishes too
    for finish in (False, True):
        newer_turn_owns_session(s, finish=finish)
        replaced = origin(s)
        assert replaced['stop_request']['id'] == fact['id'] and replaced['stop_request']['execution_generation'] == here, finish
        assert completion(s, intent)['readiness']['state'] == 'CLOSED', finish
    # pure reconstruction: reads appended no Work row and no further Stop request; the intent row itself is unchanged
    assert ledger.read_bytes() == before and len(stop_rows(s)) == 1
    assert C._intent(work(s), intent['id'])['state'] == 'ARMED'


def test_repeated_exact_stop_retains_one_request_identity(source):
    s = source
    ready_intent(s)
    remote_running(s)
    assert stop(s) == DTO and stop(s) == DTO
    [fact] = stop_rows(s)
    assert records.index(s['root']).journal_id_counts[fact['id']] == 1
    assert [row['id'] for row in turn_control.recorded_stop_requests(s['root'], 'public', s['parent']['id'], TURN)] == [fact['id']]
    assert origin(s)['stop_request']['id'] == fact['id']


def test_foreign_project_turn_session_and_generation_requests_neither_apply_nor_inherit(source):
    s = source
    _grant, _account, _candidate, intent = ready_intent(s)
    remote_running(s)
    sid, here = s['parent']['id'], generation(s)
    foreign = turn_control.stop_generation({'turn_id': TURN, 'host': FOREIGN_HOST}, TURN)
    bank_request(s, 'other', sid, TURN, here)                          # another project's namespace
    bank_request(s, 'public', sid, NEWER, here)                        # a newer turn of the same session
    bank_request(s, 'public', 'WS-another-session', TURN, here)        # another session
    bank_request(s, 'public', sid, TURN, foreign)                      # another host generation of this turn
    bank_request(s, 'public', sid, TURN, here, id='TSR-' + '0' * 24)   # a row whose identity disagrees with its fields
    assert origin(s)['stop_requested'] is False and origin(s)['stop_request'] is None
    assert origin(s)['stop_custody']['state'] == 'FOREIGN'   # the BOUND current generation refuses another generation's request
    # review PHASE-0f221e76 F2: this intent armed with no bound generation, so a foreign-generation Stop is not proven
    # irrelevant to the producer that armed: HELD, never READY
    unarmed = completion(s, intent)['readiness']
    assert unarmed['state'] == 'HELD' and 'FOREIGN_WITHOUT_ARMING_GENERATION' in [row.get('custody') for row in unarmed['reasons']]
    # the write side refuses a foreign project and an unknown turn before recording anything
    count = len(stop_rows(s))
    for over in ({'project': 'other'}, {'turn_id': 'WT-absent'}):
        with pytest.raises(ValueError, match='no active provider turn'):
            stop(s, **over)
    assert len(stop_rows(s)) == count
    # the exact generation's own Stop applies
    assert stop(s) == DTO and origin(s)['stop_request']['execution_generation'] == here
    # review F3 / Root: a Stop binds its recorded host generation; a later host generation of the same turn is not it
    child_hosts._finish_child_execution(s['root'], sid, TURN, 'interrupted')
    remote_running(s, host=THIRD_HOST)
    child_hosts._write_host(marker(s), {'turn_id': NEWER, 'requested_at': 3.0})
    rebound = origin(s)
    assert rebound['stop_request'] is None and rebound['stop_requested'] is False
    assert completion(s, intent)['readiness']['state'] == 'HELD'   # F2: unarmed intent, foreign current generation
    # Root 0709: a genuine request banked without a generation is UNBOUND evidence, never absence: HELD, not READY
    bank_request(s, 'public', sid, TURN, None)                         # a missing generation
    assert origin(s)['stop_request'] is None and origin(s)['stop_custody']['code'] == 'UNBOUND_REQUEST'
    held = completion(s, intent)['readiness']
    assert held['state'] == 'HELD' and 'PRODUCER_STOP_UNKNOWN' in [row['code'] for row in held['reasons']]
    # review F2: once newer turns replace the row and the finished record, this turn's recorded generations are
    # ambiguous (here and the foreign one): neither gains authority, and the missing one never does
    child_hosts._finish_child_execution(s['root'], sid, TURN, 'completed')
    newer_turn_owns_session(s, finish=True)
    assert generation(s) is None and origin(s)['stop_request'] is None
    assert {row['execution_generation'] for row in turn_control.recorded_stop_requests(s['root'], 'public', sid, TURN)} == {here, foreign, None}
    assert origin(s)['stop_custody']['state'] == 'UNKNOWN' and completion(s, intent)['readiness']['state'] == 'HELD'


def test_a_missing_generation_request_alone_gains_no_stop_authority_and_is_never_ready(source):
    s = source
    _grant, _account, _candidate, intent = ready_intent(s)
    bank_request(s, 'public', s['parent']['id'], TURN, None)
    newer_turn_owns_session(s, finish=True)   # no execution record names TURN at all
    assert generation(s) is None and origin(s)['stop_request'] is None and origin(s)['stop_requested'] is False
    custody = origin(s)['stop_custody']
    assert {key: custody[key] for key in ('state', 'code', 'host_record')} == {'state': 'UNKNOWN', 'code': 'UNBOUND_REQUEST', 'host_record': 'UNBOUND'}
    ready = completion(s, intent)['readiness']
    assert ready['state'] == 'HELD' and 'PRODUCER_STOP_UNKNOWN' in [row['code'] for row in ready['reasons']]


def test_unproven_stop_publication_reports_exact_truth_and_never_a_persistent_marker(source, monkeypatch):
    s = source
    ready_intent(s)
    remote_running(s)
    real = records.bank

    def unavailable(root, row, **kwargs):
        if row.get('record') == turn_control.STOP_REQUEST:
            raise OSError('journal unavailable (controlled)')
        return real(root, row, **kwargs)
    monkeypatch.setattr(turn_control.writing_records, 'bank', unavailable)
    with pytest.raises(turn_control.StopRequestUnrecorded, match='not durably recorded') as raised:
        stop(s)
    assert raised.value.stop_request['state'] == 'UNRECORDED' and 'journal unavailable' in raised.value.stop_request['error']
    assert raised.value.result == DTO   # the process Stop itself acted; only its durable record is missing
    assert 'once it is inactive' in str(raised.value)   # review F5: retry advice states its own limit
    assert child_hosts._read_host(marker(s))['turn_id'] == TURN and not stop_rows(s)
    assert origin(s)['stop_request'] is None and origin(s)['stop_marker'] is not None
    # nothing pretends the volatile marker is durable: once a newer turn replaces it, the unrecorded Stop no longer binds
    child_hosts._write_host(marker(s), {'turn_id': NEWER, 'requested_at': 2.0})
    assert origin(s)['stop_requested'] is False

    def lost_acknowledgement(root, row, **kwargs):
        result = real(root, row, **kwargs)
        if row.get('record') == turn_control.STOP_REQUEST:
            raise OSError('acknowledgement lost after the append (controlled)')
        return result
    monkeypatch.setattr(turn_control.writing_records, 'bank', lost_acknowledgement)
    assert stop(s) == DTO   # the index proves the row landed, so this is RECORDED, not a failure
    child_hosts._write_host(marker(s), {'turn_id': NEWER, 'requested_at': 3.0})
    assert len(stop_rows(s)) == 1 and origin(s)['stop_requested'] is True

    def unreadable(*_args, **_kwargs):
        raise OSError('journal index unreadable (controlled)')
    monkeypatch.setattr(turn_control, 'recorded_stop_requests', unreadable)
    with pytest.raises(turn_control.StopRequestUnrecorded, match='UNCERTAIN') as uncertain:
        stop(s)
    assert uncertain.value.stop_request['state'] == 'UNCERTAIN' and uncertain.value.result == DTO


def test_two_genuine_host_generations_hold_unknown_after_both_records_are_replaced(source):
    """The original B12 two-real-host counterexample (Stop12-current-review-002 test_actual_generation_ambiguity.py,
    sha256:971822d2): two ordinary Python host births, two genuine Stop owner writes, a completed reply racing them, then
    a newer turn replacing both the raw and the finished record. No recorded generation can be bound any more, so
    readiness is HELD with PRODUCER_STOP_UNKNOWN: never READY, never a definite Stop by inference; Continue refuses and
    a pure read appends nothing. No provider, model or network."""
    import subprocess, sys, psutil
    s = source
    _grant, _account, _candidate, intent = ready_intent(s)
    children = []
    try:
        for _ in range(2):
            children.append(subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import sys; sys.stdin.read()'],
                                             stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        hosts = [{'pid': p.pid, 'created_at': psutil.Process(p.pid).create_time()} for p in children]
        assert hosts[0] != hosts[1]
        remote_running(s, hosts[0])
        assert stop(s)['interrupted'] and len(stop_rows(s)) == 1
        child_hosts._finish_child_execution(s['root'], s['parent']['id'], TURN, 'completed')
        remote_running(s, hosts[1])
        assert stop(s)['interrupted']
        both = stop_rows(s)
        assert len(both) == 2 and len({row['execution_generation'] for row in both}) == 2
        records.bank(s['root'], {'record': 'writing-reply', 'id': 'WR-two-generation-natural-completed', 'project': 'public',
                                 'session_id': s['parent']['id'], 'turn_id': TURN, 'status': 'completed',
                                 'text': 'Controlled completion; two ordinary Python host births, no provider/model.'})
        child_hosts._begin_child_execution(s['root'], s['parent']['id'], {'turn_id': NEWER, 'project': 'public', 'state': 'RUNNING',
                                                                         'host': child_hosts._process_identity()})
        child_hosts._finish_child_execution(s['root'], s['parent']['id'], NEWER, 'completed')
        child_hosts._write_host(marker(s), {'turn_id': NEWER, 'requested_at': 3.0})
        assert generation(s) is None
        observed = origin(s)
        assert observed['terminal'] == 'completed' and observed['stop_request'] is None and observed['stop_requested'] is False
        assert observed['stop_custody']['state'] == 'UNKNOWN' and observed['stop_custody']['code'] == 'AMBIGUOUS_GENERATION'
        ledger = W._ledger(s['root'])
        before = ledger.read_bytes()
        seen = completion(s, intent)['readiness']
        assert seen['state'] != 'READY', 'Two genuine durable Stops with unresolved historical generation must not be interpreted as no Stop; fail closed/unknown.'
        assert seen['state'] == 'HELD' and 'PRODUCER_STOP_UNKNOWN' in [row['code'] for row in seen['reasons']]
        assert seen['facts']['producer_stopped'] is False and seen['facts']['producer_stop_custody'] == 'UNKNOWN'
        with pytest.raises(ValueError, match='HELD'):
            C.continue_intent(s['root'], 'public', {'intent_id': intent['id'], 'expected_basis': seen['basis']}, HUMAN)
        assert ledger.read_bytes() == before and len(stop_rows(s)) == 2
        assert C._intent(work(s), intent['id'])['state'] == 'ARMED'
    finally:
        for p in children:
            if p.stdin:
                p.stdin.close()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.terminate()
                p.wait(timeout=5)


def test_an_unbound_source_stop_is_never_reported_as_a_durable_recorded_stop(source):
    """Writer side of Root 0709: a Stop that acts while no host record names its Source producer turn cannot claim
    RECORDED, because its reader cannot honour a generationless request; it raises after acting, and the reader then
    holds (UNKNOWN) instead of reading no Stop."""
    s = source
    _grant, _account, _candidate, intent = ready_intent(s)
    newer_turn_owns_session(s, finish=True)   # no host record names TURN, so a Stop cannot bind a generation
    turn_jobs._JOBS[TURN] = {'done': False}
    try:
        with pytest.raises(turn_control.StopRequestUnrecorded, match='UNKNOWN') as raised:
            stop(s)
        assert raised.value.stop_request['state'] == 'UNBOUND' and raised.value.result == DTO
        [fact] = stop_rows(s)
        assert fact['execution_generation'] is None
        assert completion(s, intent)['readiness']['state'] == 'CLOSED'   # this process still holds the job's own Stop flag
    finally:
        turn_jobs._JOBS.pop(TURN, None)
    observed = origin(s)   # another process: no job flag, no marker, one unbound genuine request
    assert observed['stop_requested'] is False and observed['stop_custody']['code'] == 'UNBOUND_REQUEST'
    assert completion(s, intent)['readiness']['state'] == 'HELD'


def test_a_stop_of_the_arming_generation_binds_after_the_turn_acquires_a_later_generation(source):
    """Review PHASE-0f221e76 F2: the intent records the producer's host generation at arm. A genuine Stop of THAT
    generation stays CLOSED after the same turn rebinds to a later host generation and after newer turns replace both
    records; a Stop of another generation reads READY only because the arming generation is known."""
    s = source
    grant, _account, candidate = produce(s)
    remote_running(s)                          # the producer runs in a BOUND host generation G0 when it arms
    armed = generation(s)
    intent = D.handle(s['root'], 'public', arm_payload(s, grant, candidate), PRODUCER)['intent']
    _saved, reference = proof(s)
    D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'a-functional', 'reference': reference}, HUMAN)
    assert armed and C._intent(work(s), intent['id'])['origin']['execution_generation'] == {'state': 'BOUND', 'generation': armed}
    assert completion(s, intent)['intent']['origin']['execution_generation'] == armed
    sid = s['parent']['id']
    foreign = turn_control.stop_generation({'turn_id': TURN, 'host': FOREIGN_HOST}, TURN)
    bank_request(s, 'public', sid, TURN, foreign)   # another generation's genuine Stop of this turn
    assert completion(s, intent)['readiness']['state'] == 'READY'   # known arming generation G0: not the producer's Stop
    assert stop(s) == DTO                      # the genuine Stop of G0
    assert completion(s, intent)['readiness']['state'] == 'CLOSED'
    child_hosts._finish_child_execution(s['root'], sid, TURN, 'interrupted')
    remote_running(s, host=THIRD_HOST)         # the same turn rebinds to G1: current custody alone reads FOREIGN
    assert generation(s) != armed and origin(s)['stop_custody']['state'] == 'FOREIGN'
    bound = X.producer_origin(s['root'], 'public', TURN, armed_generation=armed)
    assert bound['stop_custody']['code'] == 'ARMING_GENERATION' and bound['stop_requested'] is True
    later = completion(s, intent)['readiness']
    assert later['state'] == 'CLOSED' and 'PRODUCER_STOPPED' in [row['code'] for row in later['reasons']]
    child_hosts._finish_child_execution(s['root'], sid, TURN, 'completed')
    newer_turn_owns_session(s, finish=True)    # both records replaced: the arming generation still binds
    assert completion(s, intent)['readiness']['state'] == 'CLOSED'


def test_a_stop_of_only_a_later_generation_never_becomes_the_armed_generations_stop(source):
    """Root identity review R3 (novel-predicate-results.json) on the real owners. The intent armed at G0; the same turn
    then runs in a later host generation G1 and a genuine Stop names ONLY G1. Read while G1 is the current host and again
    after newer turns replaced both host records, that Stop is neither EXACT_GENERATION nor ONLY_RECORDED_GENERATION of
    G0 (the received counterexample), and G1's live marker is not G0's Stop either: no false closure or withdrawal. The
    unarmed readings keep their existing rules; the stopped-G0 positive after replacement is the test above."""
    s = source
    grant, _account, candidate = produce(s)
    # G0 is an earlier host birth that has since exited; G1 is this live process, so the Stop owner steers the running G1
    # remotely (a Stop of an exited host is instead settled interrupted: a terminal fact, not this generation question).
    remote_running(s, host=FOREIGN_HOST)       # G0 when the producer arms
    armed = generation(s)
    intent = D.handle(s['root'], 'public', arm_payload(s, grant, candidate), PRODUCER)['intent']
    sid = s['parent']['id']
    child_hosts._finish_child_execution(s['root'], sid, TURN, 'completed')
    remote_running(s)                          # the same turn rebinds to a later, live host generation G1
    _saved, reference = proof(s)
    D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'a-functional', 'reference': reference}, HUMAN)
    later = generation(s)
    assert armed and later and later != armed
    assert stop(s) == DTO                      # a genuine Stop of G1 only
    assert [row['execution_generation'] for row in stop_rows(s)] == [later]
    assert X.producer_origin(s['root'], 'public', TURN)['stop_custody']['code'] == 'EXACT_GENERATION'   # unarmed rule unchanged
    bound = X.producer_origin(s['root'], 'public', TURN, armed_generation=armed)
    assert bound['stop_custody']['state'] == 'FOREIGN' and bound['stop_custody']['code'] == 'OTHER_THAN_ARMING_GENERATION'
    assert bound['stop_request'] is None and bound['stop_requested'] is False
    seen = completion(s, intent)['readiness']
    assert seen['state'] != 'CLOSED' and 'PRODUCER_STOPPED' not in [row['code'] for row in seen['reasons']]
    child_hosts._finish_child_execution(s['root'], sid, TURN, 'completed')
    newer_turn_owns_session(s, finish=True)    # both host records replaced: G1 is the only recorded generation
    assert X.producer_origin(s['root'], 'public', TURN)['stop_custody']['code'] == 'ONLY_RECORDED_GENERATION'
    replaced = X.producer_origin(s['root'], 'public', TURN, armed_generation=armed)
    assert replaced['stop_custody']['code'] == 'OTHER_THAN_ARMING_GENERATION' and replaced['stop_requested'] is False
    again = completion(s, intent)['readiness']
    assert again['state'] != 'CLOSED' and C._intent(work(s), intent['id'])['state'] == 'ARMED'


def test_the_arming_generation_rule_is_one_predicate_for_requests_and_live_evidence(monkeypatch):
    """The exact received predicate inputs (Root novel_predicates.py, mocked request/host custody) and their neighbours:
    armed G0 with only a G1 request is FOREIGN under a current G1 host, a replaced (UNBOUND) host and an unreadable one;
    a G0 request still binds; a generationless request stays UNKNOWN; unarmed readings are unchanged. Live job/marker
    evidence obeys the same rule: it is G0's Stop only while the host binds G0, and is UNKNOWN when unattributable."""
    from pathlib import Path
    g0, g1 = 'sha256:' + '0' * 64, 'sha256:' + '1' * 64
    def custody(requests, host, armed):
        monkeypatch.setattr(turn_control, 'recorded_stop_requests', lambda *a: requests)
        monkeypatch.setattr(turn_control, 'generation_custody', lambda *a: host)
        return X._stop_custody(Path('/unused'), 'p', {'session_id': 'WS'}, 'WT', armed=armed)
    later = [{'id': turn_control.stop_request_id('p', 'WS', 'WT', g1), 'execution_generation': g1}]
    hosts = ({'state': 'BOUND', 'generation': g1}, {'state': 'UNBOUND', 'generation': None}, {'state': 'UNREADABLE', 'generation': None})
    for host in hosts:
        row, seen = custody(later, host, g0)
        assert row is None and (seen['state'], seen['code']) == ('FOREIGN', 'OTHER_THAN_ARMING_GENERATION'), host
    assert custody(later, hosts[0], None)[1]['code'] == 'EXACT_GENERATION'
    assert custody(later, hosts[1], None)[1]['code'] == 'ONLY_RECORDED_GENERATION'
    own = [{'id': turn_control.stop_request_id('p', 'WS', 'WT', g0), 'execution_generation': g0}, *later]
    for host in hosts:
        row, seen = custody(own, host, g0)
        assert row['execution_generation'] == g0 and seen['code'] == 'ARMING_GENERATION'
    unbound = [{'id': turn_control.stop_request_id('p', 'WS', 'WT', None), 'execution_generation': None}, *later]
    assert custody(unbound, hosts[0], g0)[1]["state"] == 'UNKNOWN' and custody(unbound, hosts[0], g0)[1]['code'] == 'UNBOUND_REQUEST'
    none = {'state': 'NONE', 'code': 'NO_REQUEST', 'requests_total': 0}
    turn = {'session_id': 'WS'}
    monkeypatch.setattr(turn_control, 'generation_custody', lambda *a: {'state': 'BOUND', 'generation': g0})
    assert X._armed_live_stop(Path('/unused'), turn, 'WT', g0, None, none) == (True, none)
    monkeypatch.setattr(turn_control, 'generation_custody', lambda *a: {'state': 'BOUND', 'generation': g1})
    assert X._armed_live_stop(Path('/unused'), turn, 'WT', g0, None, none) == (False, none)
    monkeypatch.setattr(turn_control, 'generation_custody', lambda *a: {'state': 'UNBOUND', 'generation': None})
    live, held = X._armed_live_stop(Path('/unused'), turn, 'WT', g0, None, none)
    assert live is False and (held['state'], held['code']) == ('UNKNOWN', 'LIVE_STOP_UNATTRIBUTED')


def test_selected_stop_request_is_no_source_account_stop_and_grants_nothing(source):
    s = source
    grant, account, candidate, intent = ready_intent(s)
    before = X.status(s['root'], account)
    remote_running(s)
    assert stop(s) == DTO
    after = X.status(s['root'], account)
    assert after['state'] == before['state'] and after['state'] in ('ACTIVE', 'READY') and after['stop_reason'] is None
    keys = ('admitted', 'remaining', 'app_admissions', 'sessions')
    assert {key: after[key] for key in keys} == {key: before[key] for key in keys}
    _idx, rows = records.source_execution_metadata(s['root'], 'public', account['commission_id'])
    assert not [row for row in rows if row['record'] in (turn_control.STOP_REQUEST, 'writing-source-execution-stop')]
    # the request withdraws only the producer's own continuation: it cannot arm again, and nothing is admitted for it
    with pytest.raises(ValueError, match='already ended'):
        D.handle(s['root'], 'public', arm_payload(s, grant, candidate, request_id='public-after-durable-stop', obligation_id='guide'), PRODUCER)
    assert completion(s, intent)['readiness']['state'] == 'CLOSED'
