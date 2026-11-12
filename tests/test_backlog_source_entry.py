"""Focused owner entry join only; app4 functional/Source/publication proofs retained."""
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import pytest
from laplace.work import project_work as W, owner_discovery as O, backlog as B
from test_source_inputs_projection import public_root, LENS


def seed(tmp_path):
    root=public_root(tmp_path)
    W.task(LENS,{'id':'context','title':'Public Source reading context','goal':'Inspect exact current source; no execution.'},root)
    W.task('orphan',{'id':'unregistered','title':'Public unregistered Work','goal':'Read metadata without a project capability.'},root)
    return root


def test_explicit_registered_filter_issues_actual_scoped_source_entry(tmp_path):
    root=seed(tmp_path)
    global_read=W.read('',{'view':'catalogue'},root)
    assert global_read['source_inspector_read']['request']=={'facet':'source-kernel','view':'contracts'}
    selected=W.read('',{'view':'catalogue','namespace':LENS},root)
    issued=selected['source_inspector_read'];assert issued['request']=={'facet':'source-kernel','view':'contracts','namespace':LENS}
    # Consume actual issued metadata across the existing HTTP door; no body or
    # application effects. The app4 evaluator already proves body/door parity.
    from laplace.web import project_work_surface
    url=urlsplit(issued['http']['url']);code,_,raw=project_work_surface.handle(url.path,parse_qs(url.query),'GET',repo_root=root)
    assert code==200,raw
    chooser=json.loads(raw);assert chooser['scope']['namespace']==LENS
    contract=next(r for r in chooser['contracts'] if r['reference']['identity']['operation']=='work_review.followup')
    assert contract['inventory_read']['request']['project_lens']==LENS
    assert contract['inventory_read']['request']['projection']=='inputs'
    assert global_read['source_inspector_read']['request']=={'facet':'source-kernel','view':'contracts'}
    assert W.read('',{'view':'catalogue'},root)['source_inspector_read']['request']==global_read['source_inspector_read']['request']
    (tmp_path/'entry-proof.json').write_text(json.dumps({'global':global_read['source_inspector_read'],'selected':issued,'contract':contract,'filter_does_not_change_original_handle':True},indent=2))


def test_unregistered_unknown_and_unreadable_project_keep_global_entry(tmp_path,monkeypatch):
    root=seed(tmp_path)
    for namespace in ['orphan','not-recorded']:
        value=W.read('',{'view':'catalogue','namespace':namespace},root)
        assert 'namespace' not in value['source_inspector_read']['request']
    from laplace.pipeline import registry
    for failure in [None,OSError('Public unavailable registration')]:
        def unavailable(*args,**kwargs):
            if isinstance(failure,Exception):raise failure
            return failure
        monkeypatch.setattr(registry,'resolve',unavailable)
        value=W.read('',{'view':'catalogue','namespace':LENS},root)
        assert 'namespace' not in value['source_inspector_read']['request']


def test_foreign_native_filter_refuses_and_native_scope_gets_no_human_entry(tmp_path):
    root=seed(tmp_path)
    with pytest.raises(ValueError,match='actual native project scope'):
        W.read('orphan',{'view':'catalogue','namespace':LENS},root,mode='work')
    own=W.read(LENS,{'view':'catalogue'},root,mode='work')
    assert 'source_inspector_read' not in own
