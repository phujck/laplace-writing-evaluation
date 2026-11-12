"""Eigen continuity A: one Work continuity owner through the SDK, native and HTTP doors.

The real B owner on the existing public Source fixture. Reads compare the same owner facts across doors (the live
account observation timestamp is excluded); invalid, foreign and oversized requests refuse without effects, and the
SDK facade carries only owner-issued continuity actions. No provider, model, network or private data.
"""
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from test_source_use_joins import source  # noqa: F401  (the public Source fixture)
from test_eigen_continuity_owner import produce, arm_payload, end_producer, proof, PRODUCER
from laplace import sdk
from laplace.web import project_work_surface as H
from laplace.work import development_source as D, project_work as W, project_work_continuity as C
from laplace.work.owner_discovery import owned_workspace, project_scope
from laplace.writing import operations as O

STABLE = ('schema_version', 'part', 'subject', 'title', 'goal', 'standing', 'basis', 'production', 'completion', 'review',
          'delivery', 'next', 'reads', 'coverage', 'intent', 'readiness', 'proofs', 'ok', 'recorded', 'errors',
          'errors_total', 'payload_bytes')


def armed(s):
    grant, _account, candidate = produce(s)
    intent = D.handle(s['root'], 'public', arm_payload(s, grant, candidate), PRODUCER)['intent']
    end_producer(s)
    return intent


def http(s, issued):
    url = issued['http']['url'] if isinstance(issued, dict) else issued
    parts = urlsplit(url)
    code, _kind, body = H.handle(parts.path, parse_qs(parts.query, keep_blank_values=True), 'GET', b'', repo_root=s['root'])
    return code, json.loads(body)


def native(s, payload):
    return O._execute(s['root'], 'public', 'work', 'project', dict(payload))


def stable(view):
    # JSON-normalised so an in-process tuple and its HTTP list compare as the same owner fact
    return json.loads(json.dumps({key: view.get(key) for key in STABLE}, sort_keys=True, default=str))


def test_one_continuity_owner_read_through_sdk_native_and_http(source):
    s = source
    intent = armed(s)
    issued = C.handle('public', 'work', {'part': 'summary'})
    owner = C.read(s['root'], project_scope('public', 'native'), 'public', 'work', {'part': 'summary'})
    code, via_http = http(s, issued)
    assert code == 200
    views = (native(s, issued['payload']), via_http, sdk.work_read(issued['payload'], root=s['root']),
             sdk.work_continuity('public', 'work', root=s['root']))
    for view in views:
        assert stable(view) == stable(owner)
    assert owner['next']['kind'] == 'attach-proof' and owner['next']['action']['payload']['intent_id'] == intent['id']
    deeper = C.handle('public', 'work', {'part': 'completion', 'intent_id': intent['id']})
    assert stable(native(s, deeper['payload'])) == stable(http(s, deeper)[1]) == stable(sdk.work_read(deeper['payload'], root=s['root']))


def issued_by_owner(detail, scope):
    """The B owner's own detail issuer (corrected B, 40a038): the handle carries the actual Scope and no gap."""
    handle = detail['continuity_read']
    assert detail.get('continuity_read_gap') is None and handle['scope'] == scope.public()
    assert handle['operation'] == 'project' and handle['payload']['view'] == 'continuity' and handle['payload']['id'] == 'work'
    return handle


def test_selected_detail_carries_the_owner_issued_continuity_read_from_the_actual_scope(source):
    s = source
    armed(s)
    through_native = issued_by_owner(native(s, {'view': 'detail', 'id': 'work'}), project_scope('public', 'native'))
    code, body = http(s, '/work/state?project=public&view=detail&id=work')
    assert code == 200
    through_http = issued_by_owner(body, owned_workspace('http'))
    through_sdk = issued_by_owner(sdk.work_read({'namespace': 'public', 'view': 'detail', 'id': 'work'}, root=s['root']), owned_workspace('sdk'))
    # the doors add no handle of their own: each one is the owner's, followed as issued
    for handle in (through_native, through_http, through_sdk):
        code, followed = http(s, handle)
        assert code == 200 and followed['subject']['qualified_id'] == 'public::work'
        assert stable(native(s, handle['payload'])) == stable(followed)
    assert 'continuity_read' not in native(s, {'view': 'summary'})


def test_actual_scope_and_closed_requests_refuse_on_every_door(source):
    s = source
    armed(s)
    ledger = W._ledger(s['root']).read_bytes()
    with pytest.raises(ValueError, match='scope'):
        native(s, {'namespace': 'other', 'view': 'continuity', 'id': 'work', 'request': {'part': 'summary'}})
    for bad in ({'part': 'summary', 'extra': 1}, {'part': 'completion'}, {'part': 'nothing'}):
        issued = C.handle('public', 'work', bad)
        with pytest.raises(ValueError):
            native(s, issued['payload'])
        assert http(s, issued)[0] == 422
        with pytest.raises(ValueError):
            sdk.work_read(issued['payload'], root=s['root'])
    with pytest.raises(ValueError, match='unavailable'):
        native(s, {'view': 'continuity', 'id': 'absent', 'request': {'part': 'summary'}})
    duplicate = '/work/state?project=public&view=continuity&id=work&request=' + '%7B%22part%22%3A%22summary%22%2C%22part%22%3A%22summary%22%7D'
    assert http(s, duplicate)[0] == 422
    assert http(s, '/work/state?project=public&view=continuity&view=continuity&id=work')[0] == 422
    assert http(s, C.handle('public', 'work', {'part': 'summary', 'as_of': 'sha256:' + '0' * 64}))[0] == 409
    assert W._ledger(s['root']).read_bytes() == ledger


def test_pure_preflight_parity_and_an_oversized_payload_records_nothing(source):
    s = source
    armed(s)
    oversized = {'id': 'work', 'phase': 'review', 'request_id': 'REVIEW-public-door', 'summary': 'x' * 2001,
                 'findings': [{'id': 'F%d' % n, 'summary': 's'} for n in range(21)]}
    ledger = W._ledger(s['root']).read_bytes()
    issued = C.handle('public', 'work', {'part': 'preflight', 'payload': oversized})
    results = [native(s, issued['payload']), http(s, issued)[1], sdk.work_read(issued['payload'], root=s['root'])]
    for result in results:
        assert result['ok'] is False and result['recorded'] is False and result['errors_total'] >= 2
        assert stable(result) == stable(results[0])
    assert W._ledger(s['root']).read_bytes() == ledger


def test_sdk_facade_carries_only_issued_continuity_actions(source):
    s = source
    intent = armed(s)
    ledger = W._ledger(s['root']).read_bytes()
    zero = 'sha256:' + '0' * 64
    for action in ({'operation': 'development_source', 'payload': {'action': 'grant'}},
                   {'operation': 'development_source', 'payload': {'action': 'arm'}},
                   {'operation': 'work_review', 'payload': {'action': 'continue'}},
                   {'operation': 'work_delivery', 'payload': {'action': 'submit'}},
                   {'operation': 'work_delivery', 'payload': {'action': 'continue', 'project': 'other', 'intent_id': intent['id'], 'expected_basis': zero}},
                   {'operation': 'work_delivery', 'payload': {'action': 'continue'}, 'origin': 'native'},
                   'work_delivery continue'):
        with pytest.raises(ValueError):
            sdk.work_action('public', action, root=s['root'])
    assert W._ledger(s['root']).read_bytes() == ledger
    template = sdk.work_continuity('public', 'work', root=s['root'])['next']['action']
    _saved, reference = proof(s)
    arrived = sdk.work_action('public', {'operation': template['operation'], 'payload': {**template['payload'], 'reference': reference}}, root=s['root'])
    assert arrived['ok'] and arrived['proof']['attached_origin'] == 'human'   # the local operator door, never a native origin
    ready = sdk.work_continuity('public', 'work', root=s['root'])
    assert ready['next']['kind'] == 'continue' and ready['next']['callable'] is True
    stale = {'operation': 'work_delivery', 'payload': {**ready['next']['action']['payload'], 'expected_basis': zero}}
    before = W._ledger(s['root']).read_bytes()
    with pytest.raises(W.WorkConflict):
        sdk.work_action('public', stale, root=s['root'])
    assert W._ledger(s['root']).read_bytes() == before
