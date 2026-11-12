"""A writing process serves one frontend bundle while project reads remain live."""
import json
from pathlib import Path
import pytest
from laplace.web import scanner, shared_ui
from laplace.manuscript import walk
from laplace.desktop import writing_app


def fixture(tmp_path,monkeypatch):
    static=tmp_path/'static_shared';static.mkdir()
    (static/'workspace.mjs').write_text("import './old.mjs'; export const version='old';")
    (static/'old.mjs').write_text("export const old=1;")
    (static/'workspace.css').write_text('body{color:old}')
    (static/'fonts').mkdir();(static/'fonts'/'reader.woff2').write_bytes(b'old font')
    project=tmp_path/'pipeline.html';project.write_text('<main>old project</main>')
    page=tmp_path/'walk.html';page.write_text('<main>old walk __WALK_CORPUS__</main>')
    monkeypatch.setattr(shared_ui,'_STATIC',static)
    monkeypatch.setattr(shared_ui,'_ASSETS',{'workspace.mjs':'text/javascript','old.mjs':'text/javascript','workspace.css':'text/css'})
    return static,{'project':project,'walk':page}


def get(handler_type,path):
    handler=handler_type.__new__(handler_type);handler.path=path;responses=[]
    handler._send=lambda status,body,ctype:responses.append((status,ctype,body))
    handler.do_GET()
    assert len(responses)==1
    return responses[0]


def test_old_process_keeps_old_assets_while_fresh_bundle_adds_new_import_and_file_together(tmp_path,monkeypatch):
    static,pages=fixture(tmp_path,monkeypatch);old=shared_ui.capture_asset_snapshot(templates=pages)
    handler=scanner.make_handler(shared_assets=old)
    (static/'workspace.mjs').write_text("import './new.mjs'; export const version='new';")
    (static/'new.mjs').write_text('export const newValue=2;')
    shared_ui._ASSETS['new.mjs']='text/javascript'
    (static/'workspace.css').write_text('body{color:new}')
    assert b"version='old'" in get(handler,'/shared/workspace.mjs')[2]
    assert get(handler,'/shared/new.mjs')[0]==404
    assert get(handler,'/shared/workspace.css')[2]==b'body{color:old}'
    fresh=shared_ui.capture_asset_snapshot(templates=pages);new_handler=scanner.make_handler(shared_assets=fresh)
    assert old.digest!=fresh.digest
    assert b"import './new.mjs'" in get(new_handler,'/shared/workspace.mjs')[2]
    assert get(new_handler,'/shared/new.mjs')[2]==b'export const newValue=2;'
    assert get(new_handler,'/shared/workspace.css')[2]==b'body{color:new}'
    assert shared_ui.handle('/shared/new.mjs',{})[0]==200,'ordinary scanner remains live'
    with pytest.raises(TypeError):old.assets['workspace.mjs']=('text/javascript',b'changed')


def test_entry_html_and_fonts_are_pinned_but_corpus_binding_and_data_are_live(tmp_path,monkeypatch):
    static,pages=fixture(tmp_path,monkeypatch);snapshot=shared_ui.capture_asset_snapshot(templates=pages)
    handler=scanner.make_handler(shared_assets=snapshot)
    pages['project'].write_text('new project');pages['walk'].write_text('new walk')
    (static/'fonts'/'reader.woff2').write_bytes(b'new font')
    assert get(handler,'/project?workspace=writing')[2]==b'<main>old project</main>'
    assert get(handler,'/walk?corpus=first')[2]==b'<main>old walk first</main>'
    assert b'&lt;tag&gt;' in get(handler,'/walk?corpus=%3Ctag%3E')[2]
    assert get(handler,'/shared/fonts/reader.woff2')[2]==b'old font'
    data={'revision':1};monkeypatch.setattr(shared_ui,'plan_payload',lambda _:dict(data))
    assert json.loads(get(handler,'/shared/plan?corpus=book')[2])['revision']==1
    data['revision']=2
    assert json.loads(get(handler,'/shared/plan?corpus=book')[2])['revision']==2
    monkeypatch.setattr(walk,'handle',lambda path,*args:(200,'application/json',json.dumps(data).encode()))
    assert json.loads(get(handler,'/walk/doc?corpus=book')[2])['revision']==2
    data['revision']=3
    assert json.loads(get(handler,'/walk/asset?file=figure.png')[2])['revision']==3
    assert get(handler,'/shared/../walk.html')[0]==404


def test_snapshot_is_per_handler_and_health_names_exact_frontend_identity(tmp_path,monkeypatch):
    static,pages=fixture(tmp_path,monkeypatch);snapshot=shared_ui.capture_asset_snapshot(templates=pages)
    monkeypatch.setattr(scanner,'_writing_response',lambda *args:(200,'application/json',b'{"pid":123}'))
    captured=scanner.make_handler(shared_assets=snapshot);live=scanner.make_handler()
    (static/'workspace.mjs').write_text('new source')
    assert get(live,'/shared/workspace.mjs')[2]==b'new source'
    assert get(captured,'/shared/workspace.mjs')[2]!=b'new source'
    health=json.loads(get(captured,'/authoring/health')[2]);assert health['frontend_bundle']==snapshot.identity
    assert 'frontend_bundle' not in json.loads(get(live,'/authoring/health')[2])


def test_writing_startup_captures_before_binding_without_starting_a_service(tmp_path,monkeypatch):
    static,pages=fixture(tmp_path,monkeypatch);capture=shared_ui.capture_asset_snapshot;events=[]
    monkeypatch.delenv('LAPLACE_WRITING_APP',raising=False)
    def snapshot():events.append('snapshot');return capture(templates=pages)
    monkeypatch.setattr(shared_ui,'capture_asset_snapshot',snapshot)
    class Server:
        def __init__(self,address,handler):
            events.append('bind');self.handler=handler
        def serve_forever(self):
            events.append('serve');assert get(self.handler,'/shared/workspace.css')[2]==b'body{color:old}'
    monkeypatch.setattr(scanner,'_EngineServer',Server)
    scanner.serve(port=0,writing=True)
    assert events==['snapshot','bind','serve']


def test_shared_observation_presenter_is_in_the_served_import_closure():
    snapshot=shared_ui.capture_asset_snapshot()
    name='workspace-material-observation.mjs'
    assert name in snapshot.assets
    for caller in ['workspace-work.mjs','workspace-material.mjs','workspace-app.mjs']:
        assert name.encode() in snapshot.assets[caller][1]
    status,_,body=get(scanner.make_handler(shared_assets=snapshot),'/shared/'+name)
    assert status==200 and body==snapshot.assets[name][1]


def test_snapshot_refuses_unregistered_import_before_binding_and_preserves_old_bytes(tmp_path,monkeypatch):
    static,pages=fixture(tmp_path,monkeypatch)
    pages['project'].write_text('<script type="module" src="/shared/workspace.mjs"></script>')
    old=shared_ui.capture_asset_snapshot(templates=pages)
    (static/'workspace.mjs').write_text("import './missing.mjs'; export const version='broken';")
    (static/'missing.mjs').write_text('export const existingButUnregistered=1;')
    with pytest.raises(ValueError,match='missing.mjs'):
        shared_ui.capture_asset_snapshot(templates=pages)
    assert old.assets['workspace.mjs'][1]==b"import './old.mjs'; export const version='old';"
    assert shared_ui.handle('/shared/missing.mjs',{},snapshot=old)[0]==404


def test_snapshot_checks_captured_imports_and_never_rereads_dependency_files(tmp_path,monkeypatch):
    static,pages=fixture(tmp_path,monkeypatch)
    pages['project'].write_text('<script type="module" src="/shared/workspace.mjs"></script>')
    opened=[];original=Path.read_bytes
    def observed(path):
        opened.append(path.resolve());return original(path)
    monkeypatch.setattr(Path,'read_bytes',observed)
    shared_ui.capture_asset_snapshot(templates=pages)
    assert opened.count((static/'workspace.mjs').resolve())==1
    assert opened.count((static/'old.mjs').resolve())==1
    (static/'old.mjs').unlink()
    with pytest.raises(ValueError,match='old.mjs'):
        shared_ui.capture_asset_snapshot(templates=pages)



def test_snapshot_traversal_visits_cycles_once_and_ignores_dormant_modules(tmp_path,monkeypatch):
    static,pages=fixture(tmp_path,monkeypatch)
    pages['project'].write_text('<script type="module" src="/shared/workspace.mjs"></script>')
    (static/'old.mjs').write_text("import('./workspace.mjs'); export const old=1;")
    (static/'dormant.mjs').write_text("import './unregistered.mjs';")
    shared_ui._ASSETS['dormant.mjs']='text/javascript'
    snapshot=shared_ui.capture_asset_snapshot(templates=pages)
    result=shared_ui.validate_asset_snapshot(snapshot)
    assert result['reachable']==['old.mjs','workspace.mjs']
    assert result['local_import_edges']==2
    (static/'old.mjs').write_text("import '../outside.mjs';")
    with pytest.raises(ValueError,match='leaves /shared/'):
        shared_ui.capture_asset_snapshot(templates=pages)



def test_snapshot_literal_import_contract_does_not_pretend_to_validate_computed_javascript(tmp_path,monkeypatch):
    static,pages=fixture(tmp_path,monkeypatch)
    pages['project'].write_text('<script type="module" src="/shared/workspace.mjs"></script>')
    (static/'workspace.mjs').write_text("import './old.mjs'; const pending=import('./'+'computed.mjs');")
    snapshot=shared_ui.capture_asset_snapshot(templates=pages)
    assert shared_ui.validate_asset_snapshot(snapshot)['reachable']==['old.mjs','workspace.mjs']
