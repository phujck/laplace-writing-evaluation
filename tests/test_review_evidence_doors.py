"""Public Work read parity and rejected effect payloads; no caller authority from JSON."""
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from laplace import sdk
from laplace.work import project_work as W, project_work_views as V
from laplace.web import project_work_surface as H


def test_sdk_reads_exact_work_handle_and_refuses_other_families_before_lookup(tmp_path, monkeypatch):
    W.task('public', {'id': 'work', 'title': 'Read public review evidence',
                     'goal': 'Keep the exact purpose Ω'}, tmp_path)
    handle = V.handle('public', {'view': 'detail', 'id': 'work'})
    result = sdk.work_read(handle['payload'], root=tmp_path)
    url = urlsplit(handle['http']['url'])
    code, _, raw = H.handle(url.path, parse_qs(url.query), 'GET', repo_root=tmp_path)
    human = json.loads(raw)
    # Existing rich detail issues fresh planning-action request IDs on each read.
    assert code == 200
    assert {k: v for k, v in result.items() if k != 'allowed_actions'} == {
        k: v for k, v in human.items() if k != 'allowed_actions'}
    assert result['task']['title'] == 'Read public review evidence'
    before = W._ledger(tmp_path).read_bytes()
    calls = []
    monkeypatch.setattr(V, 'read', lambda *a, **k: calls.append((a, k)))
    for payload in ({'action': 'planning'}, {'view': 'discovery', 'request': {}},
                    {'view': 'workflow-definitions', 'request': {}},
                    {'view': 'sealed-text-reader', 'request': {}}, handle):
        with pytest.raises(ValueError, match='readonly project Work'):
            sdk.work_read(payload, root=tmp_path)
    assert not calls and W._ledger(tmp_path).read_bytes() == before


def test_sdk_source_inventory_projection_is_opt_in_existing_owner_contract(tmp_path):
    from laplace import system
    root = tmp_path
    (root/'src/laplace/system').mkdir(parents=True)
    (root/'src/public').mkdir()
    (root/'src/public/module.py').write_text('PUBLIC_SOURCE = 1\n')
    (root/'project').mkdir()
    (root/'registry_projects.json').write_text(json.dumps({'projects':[
        {'name':'public','kind':'project','project_dir':'project'}]}))
    owner = {'id':'core.public','kind':'core','summary':'Public source owner',
             'modules':['public.module'],'files':[],'uses':[],
             'contracts':[],'explanation':[],'evaluators':[]}
    (root/'src/laplace/system/description.json').write_text(json.dumps({
        'schema_version':system.SCHEMA,'summary':'Public declaration',
        'subsystems':[owner],'capabilities':[],
        'distributions':[{'name':'public','declaration':'pyproject.toml','packages':['public']}]}))
    reference = system.subsystem_reference(owner)
    default = sdk.source_inventory(reference, limit=2, project_lens='public', root=root)
    exact = sdk.request({'facet': 'source-inventory', 'reference': reference,
                         'limit': 2, 'project_lens': 'public', 'offset': 0}, root=root)
    assert default == exact and 'projection' not in default
    selected = sdk.source_inventory(reference, limit=2, project_lens='public',
                                    projection='inputs', root=root)
    selected_exact = sdk.request({'facet': 'source-inventory', 'reference': reference,
                                  'limit': 2, 'project_lens': 'public', 'offset': 0,
                                  'projection': 'inputs'}, root=root)
    assert selected == selected_exact and selected['projection'] == 'inputs'
    assert selected['items'] == default['items']
    with pytest.raises(ValueError, match='contract'):
        sdk.source_inventory(reference, projection='unrestricted', root=root)


def test_review_evidence_doors_carry_actual_scope_and_refuse_ambiguous_wire(tmp_path, monkeypatch):
    from laplace.native import tools
    from laplace.work import owner_discovery as O
    seen = []
    def observed(project, payload, root, **kwargs):
        scope = kwargs['native_caller']
        assert isinstance(scope, O.Scope)
        seen.append((scope.kind, scope.door, scope.namespace, project, payload))
        return {'scope_kind': scope.kind, 'scope_door': scope.door}
    monkeypatch.setattr(V, 'read', observed)
    payload = {'namespace': 'public', 'view': 'review-evidence', 'id': 'work',
               'request': {'demand': 'aggregate', 'selector': 'all'}}
    sdk.work_read(payload, root=tmp_path)
    native = tools.execute(tmp_path, 'bound', 'review', 'project', payload)
    assert native['scope_kind'] == 'project'
    query = {'project': ['public'], 'view': ['review-evidence'], 'id': ['work'],
             'request': [json.dumps(payload['request'])]}
    code, _, _ = H.handle('/work/state', query, 'GET', repo_root=tmp_path)
    assert code == 200
    assert [row[:3] for row in seen] == [('owned-workspace', 'sdk', None),
        ('project', 'native', 'bound'), ('owned-workspace', 'http', None)]
    assert seen[1][3] == 'bound' and seen[1][4]['namespace'] == 'public'
    # The owner receives the bound scope alongside the selected namespace; JSON
    # cannot turn a native project into the local SDK's owned workspace.
    before = len(seen)
    for changed in ({**query, 'id': ['work', 'other']},
                    {**query, 'view': ['detail', 'review-evidence']},
                    {**query, 'request': ['{"demand":"aggregate","demand":"support"}']}):
        code, _, _ = H.handle('/work/state', changed, 'GET', repo_root=tmp_path)
        assert code == 422
    assert len(seen) == before
    phase = {'namespace': 'public', 'view': 'review', 'id': 'work',
             'phase_id': 'phase', 'phase_revision': 'sha256:' + 'a'*64}
    tools.execute(tmp_path, 'bound', 'review', 'project', phase)
    code, _, _ = H.handle('/work/state',
        {k: [v] for k, v in {'project': 'public', **{k:v for k,v in phase.items() if k!='namespace'}}.items()},
        'GET', repo_root=tmp_path)
    assert code == 200 and [row[:3] for row in seen[-2:]] == [
        ('project', 'native', 'bound'), ('owned-workspace', 'http', None)]


def test_actual_review_evidence_owner_sdk_native_http_and_scope_refusal(tmp_path, monkeypatch):
    from laplace.native import tools
    W.task('public', {'id':'selected','title':'Read selected review evidence Ω',
        'goal':'Keep owner counts separate from body inspection',
        'review_obligations':[{'id':'source','scope':'source','label':'Source review'}]}, tmp_path)
    read = V.handle('public', {'view':'review-evidence','id':'selected',
                              'request':{'demand':'aggregate','selector':'all'}})
    local = sdk.work_read(read['payload'], root=tmp_path)
    native = tools.execute(tmp_path, 'public', 'review', 'project', read['payload'])
    url = urlsplit(read['http']['url'])
    code, _, raw = H.handle(url.path, parse_qs(url.query), 'GET', repo_root=tmp_path)
    human = json.loads(raw)
    assert code == 200
    for key in ('work','managed','counts','pending_joins','observation'):
        assert local[key] == native[key] == human[key]
    assert local['counts']['unit'] == 'review-obligation'
    assert local['counts']['required'] == local['counts']['remaining_required'] == 1
    assert 'support' not in local
    # The native host's bound project cannot be replaced by the handle namespace.
    def forbidden(*args, **kwargs):
        raise AssertionError('Foreign Work lookup happened before Scope refusal')
    monkeypatch.setattr(W, '_tasks', forbidden)
    with pytest.raises(ValueError):
        tools.execute(tmp_path, 'foreign', 'review', 'project', read['payload'])


def test_new_demand_contract_refuses_cross_demand_fields_before_leaf(tmp_path, monkeypatch):
    from laplace.native import tools
    from laplace.work import review_evidence as E
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError('Malformed request reached evidence owner')
    monkeypatch.setattr(E, 'read', forbidden)
    payload = {'namespace':'public','view':'review-evidence','id':'selected',
               'request':{'demand':'aggregate','ids':['source']}}
    with pytest.raises(ValueError):
        sdk.work_read(payload, root=tmp_path)
    with pytest.raises(ValueError):
        tools.execute(tmp_path, 'public', 'review', 'project', payload)
    code, _, _ = H.handle('/work/state', {'project':['public'],'view':['review-evidence'],
        'id':['selected'],'request':[json.dumps(payload['request'])]}, 'GET', repo_root=tmp_path)
    assert code == 422 and not calls
