"""Public, no-provider Source candidate/check/qualified-review owner controls.

Synthetic session/turn and evaluator-event rows exercise actual owner identity
lookup; they are not app admissions, model runs or review acceptance receipts.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from laplace.work import development_source as D, project_work as W, work_delivery
from laplace.writing import turn_admission, records
from laplace.projects import writing_sources


def sha(value):
    return 'sha256:' + hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'; root.mkdir()
    checkout = tmp_path / 'checkout'; checkout.mkdir()
    (root / 'project').mkdir()
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [
        {'name': 'public', 'kind': 'project', 'project_dir': 'project', 'title': 'Public Source fixture'}]}))
    (root / 'contract').mkdir()
    (root / 'profiles').mkdir()
    (root / 'profiles/writing_sources.json').write_text(json.dumps({'repositories': {'selected': str(checkout)}}))
    (checkout / 'src').mkdir()
    (checkout / 'src/answer.py').write_text('α original\nunique old\nkeep middle\nlast old\n')
    (checkout / 'evaluator.py').write_text('print("public evaluator")\n')
    (checkout / 'guide.md').write_text('Public unchanged documentation.\n')
    from dulwich.config import StackedConfig
    monkeypatch.setattr(StackedConfig, 'default', classmethod(lambda cls: cls([])))
    from dulwich.repo import Repo
    repo = Repo.init(str(checkout)); repo.hooks.clear()
    repo.get_worktree().stage([b'src/answer.py', b'evaluator.py', b'guide.md'])
    repo.get_worktree().commit(b'public Source baseline', author=b'fixture <fixture@example.invalid>',
        committer=b'fixture <fixture@example.invalid>', no_verify=True); repo.close()
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    parent = turn_admission.new_session(root, 'public', 'codex', 'gpt-6.1-sol', 'high')
    review = turn_admission.new_session(root, 'public', 'codex', 'gpt-6.1-sol', 'high', role='review')
    other = turn_admission.new_session(root, 'public', 'codex', 'gpt-6.1-sol', 'high')
    for session, ident in ((parent, 'WT-parent'), (review, 'WT-review'), (other, 'WT-other')):
        records.bank(root, {'record': 'writing-turn', 'id': ident, 'session_id': session['id'],
            'project': 'public', 'text': 'Synthetic owner boundary control', 'mode': 'review' if session['role'] == 'review' else 'work'})
    W.task('public', {'id': 'work', 'title': 'Public source change', 'goal': 'Change exact source and review it',
        'review_obligations': [{'id': 'source', 'scope': 'source', 'label': 'Source', 'inputs': ['src/answer.py', 'evaluator.py']},
                               {'id': 'guide', 'scope': 'guide', 'label': 'Guide', 'inputs': ['guide.md']}]}, root)
    binding = work_delivery.bind(root, 'public', {'action': 'bind', 'work_id': 'work',
        'expected_work_revision': W._task_revision(W._tasks('public', root)['work']), 'kind': 'app-owned',
        'provider': 'codex', 'model': 'gpt-6.1-sol', 'effort': 'high'}, {'origin': 'human'})['binding']
    profile = {'executable': '/usr/bin/python3', 'args': ['-I', 'evaluator.py'],
        'inputs': ['src/*.py', 'evaluator.py', 'guide.md'], 'fixed_inputs': {'evaluator.py': D._pin(checkout / 'evaluator.py')}}
    payload = {'action': 'grant', 'request_id': 'public-source-use-1', 'work_id': 'work',
        'expected_work_revision': W._task_revision(W._tasks('public', root)['work']), 'repository': 'selected',
        'parent_session_id': parent['id'], 'evaluator': binding['id'], 'paths': ['src/*.py', 'evaluator.py', 'guide.md'],
        'operations': ['read', 'candidate', 'apply', 'check'], 'checks': {'bounded': profile}}
    grant = D.grant(root, 'public', payload, {'origin': 'human'})['grant']
    return {'root': root, 'checkout': checkout, 'grant': grant, 'payload': payload, 'parent': parent,
            'review': review, 'binding': binding, 'door': {'origin': 'native', 'turn_id': 'WT-parent'}}


def candidate(s, **fields):
    return D.candidate(s['root'], 'public', {'grant_id': s['grant']['id'], 'files': [
        {'path': 'src/answer.py', 'before_sha256': D._pin(s['checkout'] / 'src/answer.py'), **fields}]}, s['door'])


def prepared(s):
    changed = candidate(s, edits=[{'old': 'unique old', 'new': 'new chosen'}])
    D.apply(s['root'], 'public', {'candidate_id': changed['candidate_id']}, s['door'])
    selection = {'grant_id': s['grant']['id'], 'candidate_id': changed['candidate_id']}
    pins = {p: D._pin(s['checkout'] / p) for p in ('src/answer.py', 'evaluator.py', 'guide.md')}
    return D.prepare_review_basis(s['root'], 'public', 'work', selection, pins, door=s['door'])


def test_compact_matches_legacy_identity_bytes_and_transaction(source):
    s = source; path = s['checkout'] / 'src/answer.py'; before = path.read_text()
    edits = [{'old': 'last old', 'new': ''}, {'old': 'unique old', 'new': 'last old changed'}]
    compact = candidate(s, edits=edits)
    full = candidate(s, content=before.replace('last old', '').replace('unique old', 'last old changed'))
    assert compact == full and path.read_text() == before
    row = D._latest(W._tasks('public', s['root'])['work'], 'candidate', compact['candidate_id'])
    assert row['files'][0]['content'] == before.replace('last old', '').replace('unique old', 'last old changed')
    result = D.apply(s['root'], 'public', {'candidate_id': compact['candidate_id']}, s['door'])
    assert result['effect']['state'] == 'COMMITTED'
    assert D.apply(s['root'], 'public', {'candidate_id': full['candidate_id']}, s['door'])['reused']


def test_actual_script_sized_compact_transport_and_schema(source):
    s = source; files, full = [], []
    # Public script copies only, not an implementation or edit of either real script.
    scripts = Path(__file__).resolve().parents[1] / 'scripts'
    for name in ('reembed.py', 'sewup.py'):
        raw = (scripts / name).read_text()
        path = s['checkout'] / 'src' / name; path.write_text(raw)
        old = raw.splitlines()[0]
        assert raw.count(old) == 1
        files.append({'path': 'src/' + name, 'before_sha256': sha(raw), 'edits': [{'old': old, 'new': old + ' '} ]})
        full.append({'path': 'src/' + name, 'before_sha256': sha(raw), 'content': raw.replace(old, old + ' ', 1)})
    compact_wire = {'grant_id': s['grant']['id'], 'files': files}
    full_wire = {'grant_id': s['grant']['id'], 'files': full}
    from jsonschema import validate
    validate({'action': 'candidate', **compact_wire}, D.contract())
    validate({'action': 'candidate', **full_wire}, D.contract())
    assert D.candidate(s['root'], 'public', compact_wire, s['door']) == D.candidate(s['root'], 'public', full_wire, s['door'])
    proof = {'compact_request_bytes': len(json.dumps(compact_wire).encode()), 'full_request_bytes': len(json.dumps(full_wire).encode()),
             'final_source_bytes': sum(len(f['content'].encode()) for f in full)}
    assert proof['compact_request_bytes'] < 2000 and proof['full_request_bytes'] > 150000
    (s['root'] / 'compact-transport-proof.json').write_text(json.dumps(proof, indent=2))
    assert D.source_contract()['segments']['review_basis']['schema_version'] == D.REVIEW_BASIS_SCHEMA


def test_compact_candidate_actual_native_and_http_projection(source):
    s = source
    from laplace.native import tools
    from laplace.web import project_work_surface
    payload = {'action': 'candidate', 'grant_id': s['grant']['id'], 'files': [{'path': 'src/answer.py',
        'before_sha256': D._pin(s['checkout'] / 'src/answer.py'), 'edits': [{'old': 'unique old', 'new': 'new chosen'}]}]}
    native = tools.execute(s['root'], 'public', 'work', 'development_source', payload, turn_id='WT-parent')
    code, _ctype, body = project_work_surface.handle('/work/development', {}, 'POST',
        json.dumps({'project': 'public', **payload}).encode(), s['root'])
    assert code == 200 and all(native[key] == value for key, value in json.loads(body).items())
    assert native['action_receipt']['context_refreshed'] is False
    (s['root'] / 'native-http-proof.json').write_text(json.dumps({'request': payload, 'native': native, 'http': json.loads(body)}, indent=2))


@pytest.mark.parametrize('case', ['missing', 'ambiguous', 'overlap', 'both', 'nonutf8', 'stale', 'count', 'large-result'])
def test_compact_refusals_have_no_candidate_or_source_effect(source, case):
    s = source; path = s['checkout'] / 'src/answer.py'
    if case == 'ambiguous': path.write_text('twice twice')
    if case == 'nonutf8': path.write_bytes(b'\xffunique old')
    before = path.read_bytes(); ledger = W._ledger(s['root']).read_bytes()
    fields = {'edits': [{'old': 'unique old', 'new': 'replacement'}]}
    if case == 'missing': fields['edits'][0]['old'] = 'absent'
    if case == 'ambiguous': fields['edits'][0]['old'] = 'twice'
    if case == 'overlap': fields['edits'].append({'old': 'unique old\nkeep', 'new': ''})
    if case == 'both': fields['content'] = 'dual'
    if case == 'count': fields['edits'] *= 65
    if case == 'large-result': fields['edits'][0]['new'] = 'x' * D.MAX_CANDIDATE_BYTES
    item = {'path': 'src/answer.py', 'before_sha256': sha(before), **fields}
    if case == 'stale': item['before_sha256'] = sha('other bytes')
    with pytest.raises(ValueError):
        D.candidate(s['root'], 'public', {'grant_id': s['grant']['id'], 'files': [item]}, s['door'])
    assert path.read_bytes() == before and W._ledger(s['root']).read_bytes() == ledger


def test_large_source_reuses_actual_pinned_repository_pages(source):
    s = source; path = s['checkout'] / 'src/answer.py'
    path.write_text('public λ text\n' * 6500)
    selected = D.read(s['root'], 'public', {'grant_id': s['grant']['id'], 'path': 'src/answer.py'}, s['door'])
    assert selected['text'] is None
    handle = selected['repository_read']; chunks = []
    while handle:
        page = writing_sources.execute(s['root'], handle['payload']); chunks.append(page['content'])
        assert page['page_read']['payload']['expected_sha256'] == selected['sha256']
        handle = page['read_handle']
    assert ''.join(chunks) == path.read_text()
    path.write_text('changed')
    with pytest.raises(ValueError): writing_sources.execute(s['root'], selected['repository_read']['payload'])


def test_fixed_evaluator_change_refuses_before_profile_launch(source, monkeypatch):
    s = source; (s['checkout'] / 'evaluator.py').write_text('print("changed evaluator")\n')
    monkeypatch.setattr(D, 'enforcement_available', lambda *_: None)
    monkeypatch.setattr(D, 'mount_policy_problem', lambda *_: None)
    monkeypatch.setattr(D.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('profile must not launch'))
    result = D.check(s['root'], 'public', {'grant_id': s['grant']['id'], 'name': 'bounded'}, s['door'])
    assert result['check']['state'] == 'REFUSED' and 'fixed check input changed' in result['check']['reason']


def test_returned_fixed_input_projection_is_detached(source):
    s = source
    expected = D._pin(s['checkout'] / 'evaluator.py')
    s['grant']['checks']['bounded']['fixed_inputs']['evaluator.py'] = sha('caller mutation')
    _task, row = D._find_grant(s['root'], 'public', s['grant']['id'])
    assert row['checks']['bounded']['fixed_inputs']['evaluator.py'] == expected
    assert D._public_grant(row)['checks']['bounded']['fixed_inputs']['evaluator.py'] == expected


@pytest.mark.parametrize('fixed', [{'../escape': 'sha256:' + '0' * 64}, {'evaluator.py': 'bad'},
    {'guide.md': 'sha256:' + '0' * 64}, {'outside.py': 'sha256:' + '0' * 64}])
def test_fixed_input_grant_shape_scope_and_current_bytes(source, fixed):
    s = source; payload = copy.deepcopy(s['payload']); payload['request_id'] += '-bad'
    payload['checks']['bounded']['fixed_inputs'] = fixed
    ledger = W._ledger(s['root']).read_bytes()
    with pytest.raises(ValueError): D.grant(s['root'], 'public', payload, {'origin': 'human'})
    assert W._ledger(s['root']).read_bytes() == ledger


def test_qualified_basis_consumption_subsets_detach_and_expiry(source):
    s = source; basis = prepared(s)
    stored = copy.deepcopy(basis)
    basis['pins']['guide.md'] = sha('caller mutation')
    assert D.validate_review_basis(s['root'], 'public', 'work', stored)['status'] == 'CURRENT'
    task = W._tasks('public', s['root'])['work']; grant = copy.deepcopy(D._latest(task, 'grant', s['grant']['id']))
    grant['expires_at'] = '2000-01-01T00:00:00+00:00'; W._append(s['root'], grant)
    assert D.validate_review_basis(s['root'], 'public', 'work', stored, door=s['door'])['status'] == 'CURRENT'
    with pytest.raises(D.GrantRefused):
        D.prepare_review_basis(s['root'], 'public', 'work', {k: stored[k] for k in ('grant_id', 'candidate_id')}, stored['pins'], door=s['door'])
    (s['checkout'] / 'guide.md').write_text('changed unrelated guide')
    source_pins = {p: stored['pins'][p] for p in ('src/answer.py', 'evaluator.py')}
    assert D.validate_review_basis(s['root'], 'public', 'work', stored, consumed_pins=source_pins)['status'] == 'CURRENT'
    assert D.validate_review_basis(s['root'], 'public', 'work', stored)['status'] == 'CHANGED'
    source_pins['src/answer.py'] = sha('forged consumed basis')
    assert D.validate_review_basis(s['root'], 'public', 'work', stored, consumed_pins=source_pins)['status'] == 'UNKNOWN'


def test_review_requires_actual_original_binding_revision_and_holder(source):
    s = source; basis = prepared(s); root = s['root']; door = {'origin': 'native', 'turn_id': 'WT-review'}
    with pytest.raises(ValueError, match='actual original evaluator'):
        D.validate_review_basis(root, 'public', 'work', basis, door=door)
    with pytest.raises(ValueError, match='actual Source holder'):
        D.validate_review_basis(root, 'public', 'work', basis, door={'origin': 'native', 'turn_id': 'WT-other'})
    event = {'record': work_delivery.RECORD, 'kind': work_delivery.EVENT, 'id': 'WD-synthetic-boundary',
        'project': 'public', 'work_id': 'work', 'session_id': s['review']['id'], 'state': 'ADMITTED',
        'recipient': {'id': s['binding']['id'], 'revision': 'sha256:' + '0' * 64}}
    W._append(root, event)
    with pytest.raises(ValueError): D.validate_review_basis(root, 'public', 'work', basis, door=door)
    event['recipient']['revision'] = s['binding']['revision']; W._append(root, event)
    assert D.validate_review_basis(root, 'public', 'work', basis, door=door)['status'] == 'CURRENT'
    selection = {k: basis[k] for k in ('grant_id', 'candidate_id')}
    assert D.prepare_review_basis(root, 'public', 'work', selection, basis['pins'], door=door) == basis


def test_review_identity_fence_retarget_missing_and_wrong_work(source):
    s = source; basis = prepared(s); root = s['root']
    assert D.validate_review_basis(root, 'public', 'another-work', basis)['status'] == 'UNKNOWN'
    config = root / 'profiles/writing_sources.json'; old = config.read_bytes()
    config.write_text(json.dumps({'repositories': {'selected': str(root)}}))
    assert D.validate_review_basis(root, 'public', 'work', basis)['status'] == 'CHANGED'
    config.write_bytes(old)
    (s['checkout'] / 'evaluator.py').unlink()
    assert D.validate_review_basis(root, 'public', 'work', basis)['status'] == 'UNKNOWN'
    (s['checkout'] / 'evaluator.py').symlink_to(s['checkout'] / 'guide.md')
    assert D.validate_review_basis(root, 'public', 'work', basis)['status'] == 'UNKNOWN'


def test_uncommitted_candidate_and_missing_postimage_cannot_mint_review_basis(source):
    s = source; changed = candidate(s, edits=[{'old': 'unique old', 'new': 'new chosen'}])
    selection = {'grant_id': s['grant']['id'], 'candidate_id': changed['candidate_id']}
    pins = {'evaluator.py': D._pin(s['checkout'] / 'evaluator.py')}
    with pytest.raises(ValueError, match='completed committed'):
        D.prepare_review_basis(s['root'], 'public', 'work', selection, pins, door=s['door'])
    D.apply(s['root'], 'public', {'candidate_id': changed['candidate_id']}, s['door'])
    with pytest.raises(ValueError, match='every candidate postimage'):
        D.prepare_review_basis(s['root'], 'public', 'work', selection, pins, door=s['door'])
