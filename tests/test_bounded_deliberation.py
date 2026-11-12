"""Ordinary bounded document deliberation (Eigen continuity A) beside the trusted reader-qualification purpose.

Pure owner controls only: no provider, model, network, session or private input. Provider budget flag, stdin pin,
wall, Stop/cleanup and UTF-8 output enforcement are the existing shared supervision paths that consume
``operator_profile``; these controls show which profile each purpose produces and that unsupported requests refuse
before any session, record or process. They prove no functional provider behaviour.
"""
import copy

import pytest

from laplace.core import bodies, identity
from laplace.representation import writing_bodies
from laplace.writing import records, sealed_reader as S, turn_admission as T

BASIS = 'sha256:' + '1' * 64
REF = {'schema_version': bodies.REFERENCE_SCHEMA, 'content_handle': 'sha256:' + '2' * 64, 'store': writing_bodies.STORE,
       'bytes': 10, 'encoding': bodies.ENCODING}
LIMITS = {'max_budget_usd': '3', 'wall_seconds': 480, 'cleanup_grace_seconds': 15, 'max_input_utf8_bytes': 400000,
          'max_output_utf8_bytes': 12000}


def commission(**over):
    value = {'schema_version': S.DELIBERATION_SCHEMA, 'purpose': S.DELIBERATION_PURPOSE, 'project': 'public',
             'input': copy.deepcopy(REF), 'expected_support_basis': BASIS, 'request_id': 'public-deliberation-1',
             'limits': dict(LIMITS)}
    value.update(over)
    return value


def qualification(**over):
    value = {'schema_version': 'laplace.sealed-reader-operator-commission/1', 'purpose': S.OPERATOR_PURPOSE, 'project': 'public',
             'input': copy.deepcopy(REF), 'expected_fingerprint': 'sha256:' + '3' * 64, 'expected_support_basis': BASIS,
             'request_id': 'public-qualification-1', 'limits': dict(LIMITS)}
    value.update(over)
    return value


def owners(monkeypatch, *, state='QUALIFIED', basis=BASIS, resolved=None, unchanged=True, manifest=True):
    task, packet = 'Read the public text and report findings.', 'PRIMARY DOCUMENT\nPublic fixture text.'
    monkeypatch.setattr(S, 'support', lambda root, project: {'state': state, 'support_basis': basis,
                                                             'fingerprint': 'sha256:' + '4' * 64, 'reasons': ['fixture']})
    value = {'task': 'T', 'packet': 'P', 'inputs': [{}], 'settings': {'provider': 'claude', 'model': 'opus', 'effort': 'high'},
             'sizes': {'packet': {'utf8_bytes': len(packet.encode())}}}

    def manifest_read(root, project, ref):
        if not manifest:
            raise S.InputUnavailable('No issued reader input belongs to this project.')
        return copy.deepcopy(value)
    monkeypatch.setattr(S, '_manifest', manifest_read)
    monkeypatch.setattr(S, '_get', lambda root, ref: {'T': task, 'P': packet}[ref])
    monkeypatch.setattr(S, 'settings', lambda root, model, effort: resolved or {'provider': 'claude', 'model': model, 'effort': effort})
    monkeypatch.setattr(S, 'currentness', lambda root, project, ref: {'unchanged': unchanged, 'inputs': []})
    monkeypatch.setattr(records, 'bank', lambda *a, **k: pytest.fail('a preview or refusal check records nothing'))
    return task, packet


def codes(preview):
    return [row['code'] for row in preview['refusals']]


def test_supported_limits_are_closed_and_never_raised():
    assert S.deliberation_limits(LIMITS) == LIMITS
    for key, value in (('max_budget_usd', '10.01'), ('max_budget_usd', 3), ('max_budget_usd', '0'), ('max_budget_usd', 'NaN'),
                       ('wall_seconds', 1801), ('wall_seconds', float('inf')), ('cleanup_grace_seconds', 61),
                       ('max_input_utf8_bytes', 2000001), ('max_output_utf8_bytes', 200001), ('max_output_utf8_bytes', 0)):
        with pytest.raises(ValueError):
            S.deliberation_limits({**LIMITS, key: value})
    with pytest.raises(ValueError):
        S.deliberation_limits({**LIMITS, 'attempts': 2})
    with pytest.raises(ValueError):
        S.deliberation_limits({key: value for key, value in LIMITS.items() if key != 'wall_seconds'})
    # the trusted qualification purpose keeps its own unchanged limit rule (ordinary maxima are not imposed on it)
    assert S.operator_limits({**LIMITS, 'wall_seconds': 7200})['wall_seconds'] == 7200
    policy = S.DELIBERATION_POLICY
    assert 'no hard token guarantee' in policy['stopping'] and 'no cost estimate' in policy['cost']
    assert policy['supported_maximum'] == S.DELIBERATION_MAXIMUM and policy['attempts'] == 1


def test_ordinary_request_has_its_own_purpose_and_an_immutable_intent():
    request, bounded = S.deliberation_request(commission())
    assert bounded == {'purpose': S.DELIBERATION_PURPOSE, 'limits': LIMITS, 'expected_fingerprint': None}
    assert request['profile'] == S.PROFILE and request['mode'] == 'review' and request['request_id'] == 'public-deliberation-1'
    renamed, _ = S.deliberation_request(commission(request_id='public-deliberation-2'))
    assert renamed['reader_intent_sha256'] == request['reader_intent_sha256']        # the request id is identity, not intent
    changed, _ = S.deliberation_request(commission(limits={**LIMITS, 'max_budget_usd': '2'}))
    assert changed['reader_intent_sha256'] != request['reader_intent_sha256']
    for bad in (commission(purpose=S.OPERATOR_PURPOSE), commission(schema_version='laplace.sealed-reader-operator-commission/1'),
                {**commission(), 'expected_fingerprint': BASIS}, {k: v for k, v in commission().items() if k != 'limits'},
                commission(profile=S.PROFILE), commission(expected_support_basis='not-a-pin')):
        with pytest.raises(ValueError):
            S.deliberation_request(bad)


def test_public_ordinary_start_cannot_select_a_purpose_or_the_candidate_exemption():
    ordinary = {'project': 'public', 'profile': S.PROFILE, 'input': REF, 'expected_support_basis': BASIS, 'request_id': 'public-ordinary'}
    assert S.start_request(ordinary)['profile'] == S.PROFILE   # the ordinary Start contract is unchanged
    for extra in ({'purpose': S.OPERATOR_PURPOSE}, {'purpose': S.DELIBERATION_PURPOSE}, {'limits': LIMITS}):
        with pytest.raises(ValueError):
            S.start_request({**ordinary, **extra})
    assert S.admissible_states(None) == {'QUALIFIED'}
    assert S.admissible_states({'purpose': S.DELIBERATION_PURPOSE}) == {'QUALIFIED'}
    assert S.admissible_states({'purpose': S.OPERATOR_PURPOSE}) == {'CANDIDATE', 'QUALIFIED'}


def test_bounded_dispatch_and_legacy_qualifier_compatibility():
    assert T.sealed_operator_request(qualification()) == S.operator_request(qualification())
    assert T.sealed_operator_request(qualification())[1]['purpose'] == S.OPERATOR_PURPOSE
    assert T.sealed_operator_request(commission())[1]['purpose'] == S.DELIBERATION_PURPOSE
    for bad in ({**commission(), 'purpose': 'co-design'}, None, 'document-deliberation'):
        with pytest.raises(ValueError):
            S.bounded_request(bad)
    legacy = {'operator': {'purpose': S.OPERATOR_PURPOSE, 'limits': dict(LIMITS, wall_seconds=7200), 'input_utf8_bytes': 10,
                           'stdin_sha256': BASIS, 'stdin_utf8_bytes': 5}}
    assert S.operator_profile(legacy)['purpose'] == S.OPERATOR_PURPOSE
    ordinary = {'operator': {**legacy['operator'], 'purpose': S.DELIBERATION_PURPOSE, 'limits': dict(LIMITS)}}
    assert S.operator_profile(ordinary)['limits']['cleanup_grace_seconds'] == 15
    for wrong in ({**ordinary['operator'], 'purpose': 'co-design'}, {**ordinary['operator'], 'limits': dict(LIMITS, wall_seconds=7200)}):
        with pytest.raises(ValueError):
            S.operator_profile({'operator': wrong})
    assert S.operator_profile({'profile': S.PROFILE}) is None


def test_each_entry_refuses_the_other_purpose_before_any_admission(monkeypatch):
    monkeypatch.setattr(T, '_start_scoped', lambda *a, **k: pytest.fail('no admission may start'))
    for entry, value in ((T.start_reader_deliberation, qualification()), (T.start_reader_qualification, commission()),
                         (T.start_reader_deliberation, commission(limits={**LIMITS, 'max_budget_usd': '11'}))):
        with pytest.raises(ValueError):
            entry('/public-root', value)
    started = []
    from laplace.writing import session_reads
    monkeypatch.setattr(T, '_start_scoped', lambda root, payload, **k: started.append((payload['purpose'], k)) or {'turn_id': 'WT-replayed'})
    monkeypatch.setattr(session_reads, 'session_turn_detail', lambda root, project, turn_id, view: {'turn': {'id': turn_id}})
    assert T.start_reader_deliberation('/public-root', commission())['result'] == {'turn': {'id': 'WT-replayed'}}
    assert started == [(S.DELIBERATION_PURPOSE, {'reader_operator': True})]


def test_provider_arguments_keep_the_toolless_controls_and_add_only_the_reported_budget_flag():
    profile = {'purpose': S.DELIBERATION_PURPOSE, 'limits': dict(LIMITS)}
    argv = S.claude_arguments('opus', 'high', profile)
    assert argv[:len(S.CONTROLS)] == S.CONTROLS and argv[argv.index('--max-budget-usd') + 1] == '3'
    assert argv[argv.index('--tools') + 1] == '' and '{"mcpServers":{}}' in argv and '--strict-mcp-config' in argv
    assert '--max-budget-usd' not in S.claude_arguments('opus', 'high')
    S.validate_arguments(argv, 'opus', 'high', profile)
    for other in (None, {**profile, 'limits': {**LIMITS, 'max_budget_usd': '2'}}):
        with pytest.raises(ValueError):
            S.validate_arguments(argv, 'opus', 'high', other)


def test_pure_preview_reports_support_settings_source_and_input_limits_without_recording(monkeypatch):
    task, packet = owners(monkeypatch)
    ok = S.deliberation_preview('/public-root', 'public', commission())
    assert ok['admissible'] and ok['recorded'] is False and ok['refusals'] == [] and ok['limits'] == LIMITS
    prompt = S.input_prompt(task, packet)
    assert ok['input_receipt']['stdin_sha256'] == identity.bytes_digest(prompt.encode())
    assert ok['input_receipt']['input_utf8_bytes'] == len(S.KERNEL.encode()) + len(prompt.encode())
    assert ok['start'] == {'entry': 'laplace.sdk.reader_deliberate', 'payload': commission()}
    assert ok['intent_sha256'] == S.deliberation_request(commission())[0]['reader_intent_sha256']
    tight = S.deliberation_preview('/public-root', 'public', commission(limits={**LIMITS, 'max_input_utf8_bytes': 10}))
    assert codes(tight) == ['INPUT_EXCEEDS_LIMIT'] and tight['start'] is None and not tight['admissible']
    assert codes(S.deliberation_preview('/public-root', 'public', commission(limits={**LIMITS, 'wall_seconds': 5000}))) == ['REQUEST_UNSUPPORTED']
    assert codes(S.deliberation_preview('/public-root', 'public', qualification())) == ['REQUEST_UNSUPPORTED']
    assert codes(S.deliberation_preview('/public-root', 'other', commission())) == ['PROJECT_MISMATCH']
    for patch, expected in (({'state': 'CANDIDATE'}, 'SUPPORT_UNQUALIFIED'), ({'basis': 'sha256:' + '9' * 64}, 'SUPPORT_CHANGED'),
                            ({'resolved': {'provider': 'claude', 'model': 'claude-opus-5-5', 'effort': 'high'}}, 'SETTINGS_UNSUPPORTED'),
                            ({'unchanged': False}, 'SOURCE_CHANGED_OR_UNAVAILABLE'), ({'manifest': False}, 'INPUT_UNAVAILABLE')):
        owners(monkeypatch, **patch)
        refused = S.deliberation_preview('/public-root', 'public', commission())
        assert codes(refused) == [expected] and refused['start'] is None, patch


def test_admission_refuses_candidate_support_for_the_ordinary_purpose_before_any_session(monkeypatch):
    owners(monkeypatch, state='CANDIDATE')
    monkeypatch.setattr(T, 'new_session', lambda *a, **k: pytest.fail('no session may be created'))
    request, bounded = S.deliberation_request(commission())
    with pytest.raises(S.NotAdmitted) as refused:
        S.admit('/public-root', commission(), request, None, operator=bounded)
    assert refused.value.details['reader_refusal']['code'] == 'SUPPORT_UNQUALIFIED'
    # the trusted qualification purpose keeps its CANDIDATE exemption and its exact fingerprint guard
    request, bounded = S.operator_request(qualification())
    with pytest.raises(S.NotAdmitted) as refused:
        S.admit('/public-root', qualification(), request, None, operator=bounded)
    assert refused.value.details['reader_refusal']['code'] == 'SUPPORT_CHANGED'
    owners(monkeypatch, basis='sha256:' + '9' * 64)
    request, bounded = S.deliberation_request(commission())
    with pytest.raises(S.NotAdmitted) as refused:
        S.admit('/public-root', commission(), request, None, operator=bounded)
    assert refused.value.details['reader_refusal']['code'] == 'SUPPORT_CHANGED'


def test_lost_acknowledgement_replays_the_same_receipt_and_a_changed_intent_refuses(monkeypatch):
    request, _ = S.deliberation_request(commission())
    turn = {'record': 'writing-turn', 'id': 'WT-public', 'session_id': 'WS-public', 'project': 'public',
            'request_id': request['request_id'], 'reader_intent_sha256': request['reader_intent_sha256'],
            'reader_profile': {'profile': S.PROFILE, 'manifest_id': REF['content_handle']}}

    class Saved:
        by_request = {('public', request['request_id']): [turn]}
    monkeypatch.setattr(records, 'index', lambda root: Saved)
    again = S.replay('/public-root', request)
    assert again['reused'] and again['turn_id'] == 'WT-public'
    assert again['reader_submission']['intent_sha256'] == request['reader_intent_sha256']
    changed, _ = S.deliberation_request(commission(limits={**LIMITS, 'max_output_utf8_bytes': 100}))
    with pytest.raises(ValueError, match='intent changed'):
        S.replay('/public-root', changed)


class _Condition:
    """A job condition whose first wait can raise what an interrupted or exiting caller raises."""
    def __init__(self, job, raise_first=None):
        self.job, self.raise_first, self.waits = job, raise_first, 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def wait(self, timeout=None):
        self.waits += 1
        if self.raise_first is not None and self.waits == 1:
            raise self.raise_first('caller left')
        if self.raise_first is None:
            self.job['done'] = True   # the existing supervision settles the job


def owned(monkeypatch, raise_first=None):
    from laplace.writing import session_reads, turn_control, turn_jobs
    job = {'done': False}
    job['condition'] = _Condition(job, raise_first)
    interrupted = []

    def interrupt(root, payload):
        interrupted.append(payload)
        job['done'] = True            # the existing provider interrupt/cleanup settles the job
    monkeypatch.setattr(T, '_start_scoped', lambda root, payload, **k: {'turn_id': 'WT-public', 'session_id': 'WS-public'})
    monkeypatch.setitem(turn_jobs._JOBS, 'WT-public', job)
    monkeypatch.setattr(turn_control, 'interrupt_turn', interrupt)
    monkeypatch.setattr(session_reads, 'session_turn_detail', lambda root, project, turn_id, view: {
        'turn': {'id': turn_id, 'status': 'interrupted' if interrupted else 'completed'}})
    return job, interrupted


def test_the_deliberation_entry_owns_the_turn_lifetime_until_settlement(monkeypatch):
    job, interrupted = owned(monkeypatch)
    settled = T.start_reader_deliberation('/public-root', commission())
    assert job['done'] and interrupted == []
    assert settled['purpose'] == S.DELIBERATION_PURPOSE and settled['qualification_installed'] is False
    assert settled['admission']['turn_id'] == 'WT-public' and settled['result']['turn']['status'] == 'completed'


@pytest.mark.parametrize('leaving', [KeyboardInterrupt, SystemExit])
def test_an_interrupted_or_exiting_caller_interrupts_and_settles_the_turn_first(monkeypatch, leaving):
    job, interrupted = owned(monkeypatch, raise_first=leaving)
    with pytest.raises(leaving):
        T.start_reader_deliberation('/public-root', commission())
    assert interrupted == [{'project': 'public', 'turn_id': 'WT-public'}] and job['done']


def run_result(monkeypatch, purpose, text):
    import time
    from types import SimpleNamespace
    from laplace.writing import turn_execution as E
    captured = {}
    provider = SimpleNamespace(usage_facts=None, delivery={'parts': {'task': {'state': 'DELIVERED'}}}, reader_limit_reason=None,
                               reader_operator_argv=['claude', '--max-budget-usd', '3'], process=None)

    def provider_turn(launch, held):
        held.append(provider)
        return {'status': 'completed', 'text': text}
    monkeypatch.setattr(E, '_provider_turn', provider_turn)
    monkeypatch.setattr(E, '_bank_reply', lambda launch, result: captured.setdefault('banked', result))
    monkeypatch.setattr(E, '_finish', lambda launch, result: captured.setdefault('finished', result))
    monkeypatch.setattr(E.child_hosts, '_child_execution_record', lambda root, session_id: {'provider_processes': []})
    launch = SimpleNamespace(root='/public-root', session_id='WS-public', job={'reader_started_at': time.monotonic()},
                             reader_profile={'fingerprint': 'sha256:' + '4' * 64, 'operator': {
                                 'purpose': purpose, 'limits': dict(LIMITS, max_output_utf8_bytes=10), 'input_utf8_bytes': 20,
                                 'stdin_sha256': BASIS, 'stdin_utf8_bytes': 10}})
    E.run(launch)
    assert captured['banked'] is captured['finished']
    return captured['finished']


def test_execution_records_a_purpose_correct_deliberation_receipt_with_output_clipping(monkeypatch):
    result = run_result(monkeypatch, S.DELIBERATION_PURPOSE, 'é' * 20)
    attempt = result['document_deliberation']
    assert 'reader_qualification' not in result
    assert attempt['schema_version'] == 'laplace.sealed-reader-deliberation-attempt/1'
    assert attempt['qualification_claim'].startswith('none') and 'qualification_installed' not in attempt
    assert attempt['purpose'] == S.DELIBERATION_PURPOSE and attempt['limits']['max_output_utf8_bytes'] == 10
    assert len(result['text'].encode()) <= 10 and result['text'] == 'é' * 5   # UTF-8 prefix, never a split code point
    assert result['status'] == 'interrupted' and attempt['limit_reason'] == 'operator-public-output-bytes'
    assert attempt['public_output_utf8_bytes'] == 10 and attempt['argv'] == ['claude', '--max-budget-usd', '3']
    within = run_result(monkeypatch, S.DELIBERATION_PURPOSE, 'short')
    assert within['status'] == 'completed' and within['document_deliberation']['limit_reason'] is None
    qualification = run_result(monkeypatch, S.OPERATOR_PURPOSE, 'short')
    assert 'document_deliberation' not in qualification
    assert qualification['reader_qualification']['schema_version'] == 'laplace.sealed-reader-operator-attempt/1'
    assert qualification['reader_qualification']['qualification_installed'] is False


def test_preview_and_start_report_the_same_code_for_an_oversize_input(monkeypatch):
    from laplace.core import source_pin
    from laplace.projects import library
    owners(monkeypatch)
    item = {'target': {'path': 'public.md'}, 'expected_sha256': 'sha256:' + '5' * 64, 'representation': 'utf8-text',
            'text_sha256': 't', 'body': 'b', 'derivation': 'd'}
    value = {'task': 'T', 'packet': 'P', 'inputs': [item], 'settings': {'provider': 'claude', 'model': 'opus', 'effort': 'high'},
             'sizes': {}}
    monkeypatch.setattr(S, '_manifest', lambda root, project, ref: copy.deepcopy(value))
    monkeypatch.setattr(library, '_material_target', lambda root, target: {'revision': item['expected_sha256']})
    monkeypatch.setattr(source_pin, 'check', lambda revision, guard: None)
    monkeypatch.setattr(S, '_item', lambda root, project, selected: ({k: item[k] for k in ('text_sha256', 'body', 'derivation')}, 'text'))
    monkeypatch.setattr(T, 'new_session', lambda *a, **k: pytest.fail('no session may be created'))
    small = commission(limits={**LIMITS, 'max_input_utf8_bytes': 10})
    assert codes(S.deliberation_preview('/public-root', 'public', small)) == ['INPUT_EXCEEDS_LIMIT']
    request, bounded = S.deliberation_request(small)
    with pytest.raises(S.NotAdmitted) as refused:
        S.admit('/public-root', small, request, None, operator=bounded)
    assert refused.value.details['reader_refusal']['code'] == 'INPUT_EXCEEDS_LIMIT'
