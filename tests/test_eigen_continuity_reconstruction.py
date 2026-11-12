"""Eigen continuity A: typed programme coordinate, exact canonical-Work descent and wake/SDK reconstruction.

Public fixtures only: the existing public Source fixture and a hand-written public session-memory ledger in a
temporary root. No private memory/soul/world record, client transcript, current.json, provider, model or network is
read or started.
"""
import json

import pytest

from test_source_use_joins import source  # noqa: F401  (the public Source fixture)
from test_eigen_continuity_owner import produce, arm_payload, end_producer, PRODUCER
from laplace import sdk
from laplace.engine import descent, session_memory as M
from laplace.work import development_source as D, project_work_continuity as C
from laplace.work.owner_discovery import owned_workspace, project_scope

COORD = {'kind': 'canonical-work', 'namespace': 'public', 'work_id': 'work'}


def _ledger(root, *batches):
    rows = [{'id': 'PV-public-%d' % index, 'kind': 'author-instruction', 'ruling': 'public fixture',
             'session_memory': {'schema_version': M.SCHEMA, 'changes': batch, 'sources': {}, 'acknowledged_rulings': []}}
            for index, batch in enumerate(batches)]
    (root / M.STORE).write_text(''.join(json.dumps(row) + '\n' for row in rows))


def _item(**over):
    item = {'key': M.PROGRAMME_KEY, 'kind': 'procedure', 'text': 'Continue the selected public programme through its Work owner.',
            'scope': 'public fixture', 'status': 'active', 'previous': None, 'programme': dict(COORD)}
    item.update(over)
    return item


def _armed(s):
    grant, _account, candidate = produce(s)
    intent = D.handle(s['root'], 'public', arm_payload(s, grant, candidate), PRODUCER)['intent']
    end_producer(s)
    return intent


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    root = tmp_path / 'memory-root'
    root.mkdir()
    return root


def test_programme_coordinate_is_a_closed_typed_selection_only():
    assert M.validate_programme(COORD) == COORD
    for bad in ({**COORD, 'status': 'in-progress'}, {**COORD, 'next_action': {}}, {**COORD, 'kind': 'work-order'},
                {**COORD, 'namespace': 'has space'}, {**COORD, 'work_id': 'a::b'}, {**COORD, 'work_id': 'x' * 161},
                {'kind': 'canonical-work', 'namespace': 'public'}, 'work://public/work', None):
        with pytest.raises(ValueError):
            M.validate_programme(bad)
    assert M.programme_uri(COORD) == 'work://public/work'
    assert M.parse_work_uri('work://public/work') == COORD
    for bad in ('WORK-public', 'work://public', 'work://public/work/extra', 'work:///work', 'memory://procedure/eigen-programme'):
        with pytest.raises(ValueError):
            M.parse_work_uri(bad)


def test_bare_work_ids_are_not_promoted_and_typed_work_routes_exactly():
    assert descent.normalize_target('WORK-eigen-owned-continuity-20261030') is None
    assert descent.normalize_target('work://public/work')['kind'] == 'canonical-work'
    assert descent.normalize_target('WO-20260101-public')['kind'] == 'ledger-row'   # legacy rows keep their own route
    assert descent.normalize_target('memory://procedure/eigen-programme')['kind'] == 'session-memory'
    assert 'canonical-work' in descent.KINDS


def test_authored_pointer_states_and_prior_versions_are_preserved(state):
    root = state
    assert M.programme(root)['state'] == 'ABSENT'
    first = {key: value for key, value in _item().items() if key != 'programme'}
    _ledger(root, [first])
    assert M.programme(root)['state'] == 'UNSELECTED'
    first_version = M.digest(M.canonical(first))
    second = _item(previous=first_version)
    _ledger(root, [first], [second])
    selected = M.programme(root)
    assert selected['state'] == 'SELECTED' and selected['reference'] == COORD
    assert selected['descent'] == {'kind': 'canonical-work', 'reference': 'work://public/work'}
    assert selected['entry']['version'] == M.digest(M.canonical(second))
    entry, _meta = M.get_entry(root, M.PROGRAMME_KEY)
    assert entry['previous'] == first_version and entry['programme'] == COORD
    retired = _item(previous=selected['entry']['version'], status='retired')
    _ledger(root, [first], [second], [retired])
    assert M.programme(root)['state'] == 'INACTIVE'


def test_a_recorded_malformed_pointer_is_reported_never_guessed(state):
    _ledger(state, [_item(programme={**COORD, 'status': 'done'})])
    pointer = M.programme(state)
    assert pointer['state'] == 'INVALID' and 'reference' not in pointer and 'descent' not in pointer
    _ledger(state, [_item(kind='law')])
    assert M.programme(state)['state'] == 'INVALID'


def test_apply_validates_the_coordinate_before_any_append(state):
    for change, match in (({**_item(), 'kind': 'law'}, 'procedure record'),
                          ({**_item(), 'programme': {**COORD, 'account': 'SC-public'}}, 'exactly')):
        change = {key: value for key, value in change.items() if key not in ('previous', 'status')}
        with pytest.raises(ValueError, match=match):
            M.apply(state, {'changes': [change]})
    assert not (state / M.STORE).exists()


def test_canonical_work_descent_delegates_to_the_work_owner_under_actual_scope(source, monkeypatch):
    s = source
    intent = _armed(s)
    monkeypatch.setattr(descent, 'source_tree', lambda: s['root'])
    native = project_scope('public', 'native')
    owner = C.read(s['root'], native, 'public', 'work', {'part': 'summary'})
    found = descent.descend(kind='canonical-work', reference='work://public/work', read_scope=native, content_budget=1_000_000)
    assert found['content_status'] == 'COMPLETE' and found['read_only'] and found['transition_claim'] == 'none'
    value = json.loads(found['content'])
    assert value['subject'] == owner['subject'] and value['basis']['token'] == owner['basis']['token']
    assert value['next']['kind'] == owner['next']['kind'] == 'attach-proof'
    assert found['provenance']['work'] == COORD and found['provenance']['scope']['kind'] == 'project'
    deeper = descent.descend(kind='canonical-work', read_scope=native, content_budget=1_000_000, reference=json.dumps(
        {'work': 'work://public/work', 'request': {'part': 'completion', 'intent_id': intent['id']}}))
    assert json.loads(deeper['content'])['intent']['id'] == intent['id']
    cases = (('work://public/work', None, 'SCOPE_REQUIRED'),
             ('work://public/work', project_scope('other', 'native'), 'SCOPE_REFUSED'),
             ('work://public/work', 'public', 'SCOPE_REFUSED'),
             ('work://public/absent', native, 'NOT_FOUND'),
             ('WORK-public', owned_workspace('sdk'), 'MALFORMED'),
             (json.dumps({'work': 'work://public/work', 'status': 'done'}), native, 'MALFORMED'))
    for reference, scope, code in cases:
        with pytest.raises(descent.DescentRefused) as refused:
            descent.descend(kind='canonical-work', reference=reference, read_scope=scope)
        assert refused.value.details['residue']['code'] == code, reference
    with pytest.raises(descent.DescentRefused):
        descent.descend(kind='canonical-work', reference='work://public/work', source='work_orders')


def test_session_memory_descent_names_the_typed_programme_descent(source, monkeypatch, tmp_path):
    s = source
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    monkeypatch.setattr(descent, 'source_tree', lambda: s['root'])
    _ledger(s['root'], [_item()])
    found = descent.descend(kind='session-memory', reference='memory://' + M.PROGRAMME_KEY, content_budget=1_000_000)
    assert found['programme_descent'] == {'kind': 'canonical-work', 'reference': 'work://public/work'}


def test_wake_person_and_engine_share_the_coordinate_and_one_compact_owner_observation(source, monkeypatch, tmp_path):
    s = source
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    intent = _armed(s)
    from laplace.engine import wake
    absent = wake.programme_glow(s['root'], mode='person')
    assert absent['state'] == 'ABSENT' and 'observation' not in absent and 'reads' not in absent
    _ledger(s['root'], [_item()])
    person = wake.programme_glow(s['root'], mode='person')
    engine = wake.programme_glow(s['root'], mode='engine')
    assert person['context_mode'] == 'person' and engine['context_mode'] == 'engine'
    assert {k: v for k, v in person.items() if k != 'context_mode'} == {k: v for k, v in engine.items() if k != 'context_mode'}
    seen = person['observation']
    assert person['state'] == 'SELECTED' and seen['status'] == 'OBSERVED' and seen['subject'] == 'public::work'
    assert seen['next']['kind'] == 'attach-proof' and seen['next']['callable'] is False
    assert person['reads']['continuity'] == C.handle('public', 'work', {'part': 'summary'})
    assert person['reads']['descent'] == {'kind': 'canonical-work', 'reference': 'work://public/work'}
    owner = C.read(s['root'], owned_workspace('engine-wake'), 'public', 'work', {'part': 'summary'})
    assert seen['basis_token'] == owner['basis']['token']
    text = json.dumps(person)
    assert len(text.encode()) < 6000 and intent['id'] not in json.dumps(person['pointer'])
    for private in ('soul', 'world_body', 'transcript', 'current.json', 'execution'):
        assert private not in person and private not in seen
    long = wake._programme_text('x' * 481, person['reads']['continuity'])
    assert long == {'projection': 'COARSE-GRAINED', 'chars': 481, 'descend': person['reads']['continuity']}
    assert wake._programme_text('short', {}) == 'short'


def test_fresh_sdk_process_reconstructs_the_programme_from_eigen_records(source, monkeypatch, tmp_path):
    s = source
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    _armed(s)
    assert sdk.programme(root=s['root'])['pointer']['state'] == 'ABSENT'
    _ledger(s['root'], [_item()])
    found = sdk.programme(root=s['root'])
    assert found['pointer']['state'] == 'SELECTED'
    assert found['continuity']['subject']['qualified_id'] == 'public::work'
    assert found['continuity']['next']['kind'] == 'attach-proof'
    assert found['continuity']['basis']['token'] == sdk.work_continuity('public', 'work', root=s['root'])['basis']['token']
