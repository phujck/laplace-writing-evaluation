"""The browser entry modules must fetch their captured literal import closure."""
from laplace.web import shared_ui


def test_project_module_imports_are_served_by_frozen_frontend():
    bundle=shared_ui.capture_asset_snapshot()
    closure=shared_ui.validate_asset_snapshot(bundle,entrypoints=[
        '/shared/project-work.mjs','/shared/pipeline-panes.mjs'])
    assert len(closure['reachable'])>10
    assert 'engineering-support.mjs' in closure['reachable']
    for name in closure['reachable']:
        status,content_type,body=shared_ui.handle('/shared/'+name,{},snapshot=bundle)
        assert status==200,(name,status,body)


def test_manual_resolution_module_and_dynamic_stylesheet_are_captured_and_served():
    bundle=shared_ui.capture_asset_snapshot()
    closure=shared_ui.validate_asset_snapshot(bundle)
    assert 'proposal-resolution.mjs' in closure['reachable']
    for name,kind in [('proposal-resolution.mjs','text/javascript'),('proposal-resolution.css','text/css')]:
        status,content_type,body=shared_ui.handle('/shared/'+name,{},snapshot=bundle)
        assert status==200 and content_type.startswith(kind)
        assert body==bundle.assets[name][1] and body
