"""Managed source/data selection; all data is public synthetic fixture state."""
import json
from pathlib import Path
import pytest
from laplace.desktop import managed_homes as H, writing_app as A
from laplace.core import checkout
from laplace.web import writing_server


def workspace(tmp_path):
    root = tmp_path / 'data'; root.mkdir(); (root / 'profiles').mkdir()
    (root / 'registry_projects.json').write_text('{"projects":[]}')
    return root


def test_shared_selection_legacy_and_qualified_native_locations(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'platform-state'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'platform-data'))
    root = workspace(tmp_path); code = checkout.source_tree()
    legacy = H.resolve(code, state=tmp_path / 'old.json')
    assert legacy['receipt'] == str(tmp_path / 'old.json') and legacy['engine_state'] is None
    assert legacy['native_profile'] == str(tmp_path / 'writing-native')
    a = H.resolve(code, state=tmp_path / 'A.json', workspace_root=root)
    b = H.resolve(code, state=tmp_path / 'B.json', workspace_root=root)
    assert a['native_profile'] != b['native_profile'] and H.viewer_identity(a) != H.viewer_identity(b)
    assert a['engine_state'] == str(root / '.laplace-state')
    assert H.viewer_identity(H.resolve(tmp_path / 'other-code', state=tmp_path / 'A.json', workspace_root=root)) != H.viewer_identity(a)
    assert H.resolve(code, workspace_root=root)['receipt'].startswith(str(tmp_path / 'platform-state' / 'laplace' / 'workspaces'))
    with pytest.raises(ValueError):H.resolve(code, engine_state=tmp_path / 'engine')
    with pytest.raises(ValueError):H.resolve(code, state=root, workspace_root=root)
    with pytest.raises(ValueError):H.resolve(code, workspace_root=root, engine_state=tmp_path / 'same', session_workspaces=tmp_path / 'same')


def test_separate_environment_ignores_inherited_main_state_and_legacy_is_unchanged(tmp_path, monkeypatch):
    root = workspace(tmp_path); code = checkout.source_tree(); receipt = tmp_path / 'app.json'
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'do-not-use-main-state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES', str(tmp_path / 'do-not-use-main-session'))
    homes = A.host_selection(code, receipt, workspace_root=root, engine_state=tmp_path / 'engine', session_workspaces=tmp_path / 'sessions')
    token = A._HOMES.set(homes)
    try:env = A._managed_environment(code, receipt, {'identity':'selection'}, 'source')
    finally:A._HOMES.reset(token)
    assert env['LAPLACE_STATE'] == homes['engine_state'] and env['LAPLACE_SESSION_WORKSPACES'] == homes['session_workspaces']
    assert env['LAPLACE_REPO_ROOT'] == str(root) and env['LAPLACE_WRITING_CODE_ROOT'] == str(code)
    assert json.loads(env['LAPLACE_MANAGED_HOMES']) == homes
    assert not (tmp_path / 'do-not-use-main-state').exists()
    old = A._managed_environment(code,receipt,{'identity':'selection'},'source')
    assert old['LAPLACE_STATE'].endswith('do-not-use-main-state') and 'LAPLACE_MANAGED_HOMES' not in old
    assert writing_server.default_session_workspaces(root,tmp_path/'engine') == H.default_session_workspaces(root,tmp_path/'engine')


def test_separate_receipt_and_health_scope_refuse_before_stop_or_update(tmp_path, monkeypatch):
    root=workspace(tmp_path);code=checkout.source_tree();state=tmp_path/'app.json'
    homes=A.host_selection(code,state,workspace_root=root,engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')
    record={'schema_version':A.STATE_SCHEMA,'pid':123,'start_tick':'tick','repo_root':str(code),'managed_homes':homes,
            **{key:homes[key] for key in ('code_root','workspace_root','engine_state','session_workspaces')}}
    A._write(state,record)
    monkeypatch.setattr(A,'_owned',lambda _:True)
    monkeypatch.setattr(A,'health',lambda *a,**k:{'pid':123,'source':str(root),'managed_homes':{**homes,'workspace_root':str(tmp_path/'foreign')}})
    monkeypatch.setattr(A,'_terminate_owned',lambda *a:pytest.fail('mismatched service was signalled'))
    result=A.stop(root=code,state=state,workspace_root=root,engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')
    assert result['status']=='selection-mismatch' and state.exists()
    result=A.stop(root=code,state=state)  # Legacy entrance cannot operate a separate receipt.
    assert result['status']=='selection-mismatch' and state.exists()
    result=A.status(root=code,state=state,workspace_root=root,engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')
    assert result['status']=='selection-mismatch'


def test_health_requires_consistent_code_data_state_and_consumed_basis(tmp_path):
    root=workspace(tmp_path);homes=A.host_selection(checkout.source_tree(),tmp_path/'state.json',workspace_root=root,
                                                  engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')
    basis={'root':str(root),'identity':'basis'}
    record={'pid':123,'workspace_start':basis}
    live={'pid':123,'source':str(root),'managed_homes':homes,'source_start':{'root':homes['code_root']},
          'workspace_start':basis,**{key:homes[key] for key in ('code_root','workspace_root','engine_state','session_workspaces')}}
    assert A._health_matches(live,homes,record)
    assert not A._health_matches({**live,'code_root':str(tmp_path/'foreign')},homes,record)
    assert not A._health_matches({**live,'workspace_start':{**basis,'identity':'different'}},homes,record)
    assert not A._health_matches({**live,'source_start':{'root':str(root)}},homes,record)


def test_separate_window_identity_covers_private_state_without_changing_profile(tmp_path):
    root=workspace(tmp_path);code=checkout.source_tree();receipt=tmp_path/'app.json'
    original=H.resolve(code,state=receipt,workspace_root=root,engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')
    for changes in ({'engine_state':tmp_path/'engine-other'},{'session_workspaces':tmp_path/'sessions-other'}):
        altered=H.resolve(code,state=receipt,workspace_root=root,**{'engine_state':tmp_path/'engine','session_workspaces':tmp_path/'sessions',**changes})
        assert H.viewer_identity(altered)!=H.viewer_identity(original)
        assert altered['native_profile']==original['native_profile']


def test_endpoint_activation_is_qualified_without_changing_storage_selection(tmp_path):
    homes=H.resolve(checkout.source_tree(),state=tmp_path/'app.json',workspace_root=workspace(tmp_path),
                    engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')
    before=dict(homes)
    assert 'window_id' not in homes
    assert H.viewer_identity(homes,'127.0.0.1',18881)!=H.viewer_identity(homes,'127.0.0.1',18882)
    assert H.viewer_identity(homes,'localhost',18881)!=H.viewer_identity(homes,'127.0.0.1',18881)
    assert homes==before
    legacy=H.resolve(checkout.source_tree(),state=tmp_path/'legacy.json')
    import hashlib
    expected='org.laplace.Writing.p'+hashlib.sha256((str(checkout.source_tree())+'\0'+str((tmp_path/'legacy.json').resolve())).encode()).hexdigest()[:16]
    assert H.viewer_identity(legacy,'127.0.0.1',18881)==H.viewer_identity(legacy,'localhost',18882)==expected


def test_stalled_recovery_refuses_foreign_health_before_project_execution_read(tmp_path,monkeypatch):
    root=workspace(tmp_path);code=checkout.source_tree();state=tmp_path/'app.json'
    locations={'workspace_root':root,'engine_state':tmp_path/'engine','session_workspaces':tmp_path/'sessions'}
    homes=A.host_selection(code,state,**locations)
    record={'schema_version':A.STATE_SCHEMA,'pid':123,'start_tick':'tick','repo_root':str(code),'managed_homes':homes,
            **{key:homes[key] for key in ('code_root','workspace_root','engine_state','session_workspaces')}}
    A._write(state,record);monkeypatch.setattr(A,'_owned',lambda _:True)
    monkeypatch.setattr(A,'health',lambda *a,**k:{'pid':123,'managed_homes':{**homes,'workspace_root':str(tmp_path/'foreign')}})
    from laplace.writing import child_hosts
    monkeypatch.setattr(child_hosts,'_child_execution_record',lambda *a:pytest.fail('foreign service caused a project-state read'))
    result=A.recover_stalled_turn(root=code,state=state,project='book',session_id='session',turn_id='turn',
                                 expected_pid=123,expected_start_tick='tick',**locations)
    assert result['status']=='refused' and 'selected homes' in result['reason'] and state.exists()
