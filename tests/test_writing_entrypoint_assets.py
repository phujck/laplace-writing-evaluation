"""Writing entrypoint dependencies must exist in the actual served snapshot."""
from laplace.web import shared_ui

def test_writing_entrypoint_import_closure_is_served():
    snapshot=shared_ui.capture_asset_snapshot()
    closure=shared_ui.validate_asset_snapshot(snapshot,entrypoints=[
        'project-work.mjs','pipeline-panes.mjs','walk.mjs','writing-panel.mjs'])
    assert 'engineering-support.mjs' in closure['reachable']
    for name in closure['reachable']:
        response=shared_ui.handle('/shared/'+name,{},snapshot=snapshot)
        assert response and response[0]==200,name
