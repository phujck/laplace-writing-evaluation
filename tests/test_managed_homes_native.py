"""Separate-home native consumer: actual entry/controller with isolated toolkit/transport boundaries.

No real GTK window or provider is opened. The OS-Python -I case executes the real
module/helper without importing Laplace; controller cases drive the real inner app.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace as NS

import pytest
from laplace.core import checkout
from laplace.desktop import native_writing as native
from test_native_writing import desktop_close


def workspace(path):
    path.mkdir(); (path / 'registry_projects.json').write_text('{"projects": []}')
    (path / 'profiles').mkdir(); return path


def test_separate_native_command_uses_code_and_forwards_every_effective_home(tmp_path, monkeypatch):
    code=checkout.source_tree(); data=workspace(tmp_path/'data with spaces'); receipt=tmp_path/'receipt.json'
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'platform-data'))
    monkeypatch.setenv('LAPLACE_STATE','/unselected/Main-state')
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES','/unselected/Main-sessions')
    homes=native.managed_selection(code,receipt,workspace_root=data)
    for action in ('--no-open','--reconnect','--update','--status','--stop'):
        command=native.backend_command(code,receipt,'127.0.0.1',18883,action,workspace_root=data)
        assert command[0]==str(code/'scripts/laplace-python') and command[-1]==action
        for flag,key in (('--repo-root','code_root'),('--state','receipt'),('--workspace-root','workspace_root'),('--engine-state','engine_state'),('--session-workspaces','session_workspaces')):
            assert command[command.index(flag)+1]==homes[key]
    assert homes['engine_state']==str(data/'.laplace-state')
    assert homes['session_workspaces'].startswith(str(tmp_path/'platform-data'))
    with pytest.raises(ValueError,match='workspace-root'):
        native.backend_command(code,receipt,'127.0.0.1',18883,'--status',engine_state=tmp_path/'engine')


def test_os_isolated_native_loads_real_selector_without_laplace_import(tmp_path):
    code=checkout.source_tree(); data=workspace(tmp_path/'data'); receipt=tmp_path/'receipt.json'
    script="""import json,runpy,sys
from pathlib import Path
namespace=runpy.run_path(sys.argv[1])
result=namespace['backend_command'](Path(sys.argv[2]),Path(sys.argv[3]),'127.0.0.1',18883,'--reconnect',workspace_root=Path(sys.argv[4]),engine_state=Path(sys.argv[5]),session_workspaces=Path(sys.argv[6]))
assert not any(n=='laplace' or n.startswith('laplace.') for n in sys.modules)
print(json.dumps(result))
"""
    result=subprocess.run(['/usr/bin/python3','-I','-B','-c',script,str(Path(native.__file__)),str(code),str(receipt),str(data),str(tmp_path/'engine'),str(tmp_path/'sessions')],capture_output=True,text=True,check=True,cwd=tmp_path)
    command=json.loads(result.stdout);assert command[0]==str(code/'scripts/laplace-python')
    assert command[command.index('--workspace-root')+1]==str(data)


def test_qualified_window_profile_and_ui_state_do_not_cross_receipts_or_code(tmp_path):
    code=checkout.source_tree(); data=workspace(tmp_path/'data'); a=tmp_path/'A.json'; b=tmp_path/'B.json'
    first=native.managed_selection(code,a,workspace_root=data,engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')
    second=native.managed_selection(code,b,workspace_root=data,engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')
    assert native.viewer_identity(code,first,'127.0.0.1',18883)!=native.viewer_identity(code,second,'127.0.0.1',18883)
    assert first['native_profile']!=second['native_profile']
    other=tmp_path/'code-b'; helper=other/'src/laplace/desktop/managed_homes.py';helper.parent.mkdir(parents=True);helper.write_bytes((code/'src/laplace/desktop/managed_homes.py').read_bytes())
    moved=native.managed_selection(other,a,workspace_root=data,engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')
    assert native.viewer_identity(code,first,'127.0.0.1',18883)!=native.viewer_identity(other,moved,'127.0.0.1',18883)
    assert first['native_profile']==moved['native_profile']
    origin='http://127.0.0.1:18883'; uri=origin+'/project?workspace=writing&corpus=book&view=work'
    native.write_ui_state(a,1180,800,uri,origin,homes=first)
    assert native.read_ui_state(a,origin,homes=moved)['uri']==uri
    assert native.read_ui_state(b,origin,homes=second)['uri']==origin+'/project?workspace=writing'
    assert native.ui_state_path(a)==a.with_name('A-window.json'), 'legacy location unchanged'


@pytest.mark.parametrize('desktop_close',[{'separate':True}],indirect=True)
def test_existing_primary_activation_reuses_lease_and_recovery_forwards_homes(desktop_close):
    app=desktop_close
    app.ensure_connection(manual=True)
    assert app.actions==['--reconnect']
    app.recovery.last_start-=10
    app.do_activate()
    assert app.presentations==['present'] and app.actions==['--reconnect','--reconnect']
    app.ensure_connection(manual=True,reload=True)
    assert app.actions[-1]=='--update'
    app.check_close()
    assert app.actions[-1]=='--status' and app.exited
    for args,locations in app.backend_calls:
        assert args[0]==app.test_root and args[1]==app.test_state
        assert locations=={key:str(Path(value).resolve()) for key,value in app.test_locations.items()}
    homes=native.managed_selection(app.test_root,app.test_state,**app.test_locations)
    assert native.ui_state_path(app.test_state,homes=homes).is_file()
    lease=native.acquire_native_profile(homes);lease.close()  # actual detach released the lease


@pytest.mark.parametrize('desktop_close',[{'separate':True}],indirect=True)
@pytest.mark.parametrize('drift',['code','engine_state','session_workspaces','endpoint'])
def test_incompatible_primary_refuses_held_profile_before_backend_effect(desktop_close,tmp_path,drift):
    app=desktop_close;app.ensure_connection(manual=True)
    homes=native.managed_selection(app.test_root,app.test_state,**app.test_locations)
    code_b=tmp_path/'code-b';helper=code_b/'src/laplace/desktop/managed_homes.py';helper.parent.mkdir(parents=True);helper.write_bytes((app.test_root/'src/laplace/desktop/managed_homes.py').read_bytes())
    locations=dict(app.test_locations)
    if drift not in {'code','endpoint'}:locations[drift]=tmp_path/('changed-'+drift)
    other=native.run(code_b if drift=='code' else app.test_root,app.test_state,
        port=18884 if drift=='endpoint' else 8771,**locations)
    assert other.application_kwargs['application_id']!=app.application_kwargs['application_id']
    other.window=NS(present=lambda:None,destroy=lambda:None);other.starting=False
    messages=[];other.notice=NS(set_text=messages.append,show=lambda:None);other.retry_button=NS(show=lambda:None)
    def background(work,finish):
        try:value=work()
        except Exception as exc:finish(None,str(exc))
        else:finish(value,None)
    other.background=background;before=list(app.backend_calls)
    other.ensure_connection(manual=True)
    assert app.backend_calls==before and any('profile is already in use' in text for text in messages)
    assert app.window is not None and not app.exited
    app.detach_window()
    lease=native.acquire_native_profile(homes);lease.close()


def test_native_refuses_mismatched_success_before_loading_a_workspace(tmp_path,monkeypatch):
    code=checkout.source_tree();data=workspace(tmp_path/'data');receipt=tmp_path/'r.json'
    homes=native.managed_selection(code,receipt,workspace_root=data,engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')
    monkeypatch.setattr(native.subprocess,'run',lambda *a,**k:NS(returncode=0,stdout=json.dumps({'status':'running','managed_homes':homes}),stderr=''))
    assert native.backend(code,receipt,'127.0.0.1',18883,'--status',workspace_root=data,engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')['status']=='running'
    homes['workspace_root']=str(tmp_path/'foreign')
    with pytest.raises(RuntimeError,match='another managed home'):
        native.backend(code,receipt,'127.0.0.1',18883,'--reconnect',workspace_root=data,engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')


def test_requested_homes_cannot_qualify_foreign_or_unattributed_health(tmp_path,monkeypatch):
    code=checkout.source_tree();data=workspace(tmp_path/'data');receipt=tmp_path/'r.json'
    locations={'workspace_root':data,'engine_state':tmp_path/'engine','session_workspaces':tmp_path/'sessions'}
    homes=native.managed_selection(code,receipt,**locations)
    result={'status':'stale-source','managed_homes':homes,'health':{'managed_homes':dict(homes)}}
    monkeypatch.setattr(native.subprocess,'run',lambda *a,**k:NS(returncode=0,stdout=json.dumps(result),stderr=''))
    assert native.backend(code,receipt,'127.0.0.1',18883,'--reconnect',**locations)['status']=='stale-source'
    result['health']['managed_homes']['workspace_root']=str(tmp_path/'foreign')
    with pytest.raises(RuntimeError,match='observed service'):
        native.backend(code,receipt,'127.0.0.1',18883,'--status',**locations)
    result['health']['managed_homes']=dict(homes);result['health_attribution_unproven']=True
    with pytest.raises(RuntimeError,match='observed service'):
        native.backend(code,receipt,'127.0.0.1',18883,'--status',**locations)


def test_installer_plan_freezes_shared_selection_without_installing(tmp_path):
    source=checkout.source_tree();spec=importlib.util.spec_from_file_location('homes_install',source/'scripts/install_writing_app.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    data=workspace(tmp_path/'data');receipt=tmp_path/'receipt.json'
    plan=module.render(checkout=source,desktop_path=tmp_path/'app.desktop',icon_path=tmp_path/'icon.svg',workspace_root=data,state=receipt,engine_state=tmp_path/'engine',session_workspaces=tmp_path/'sessions')
    desktop=plan['files'][0]['content'];assert '--workspace-root' in desktop and '--engine-state' in desktop and '--session-workspaces' in desktop
    assert plan['managed_homes']['receipt']==str(receipt) and str(data/'scripts/laplace-python') not in desktop
    assert not (tmp_path/'app.desktop').exists()
