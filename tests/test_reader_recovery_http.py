"""Exact current-source recovery selectors through the existing HTTP owner."""
import json

from laplace.web import project_work_surface
from laplace.manuscript import reader_restructure as owner
from test_reader_restructure import case
from test_reader_logical_publication import completed_preview, apply


def test_http_recovery_reads_typed_boolean_and_explicit_occurrence_array(case, monkeypatch):
    root, _, chapter = case
    final = completed_preview(case)[1]
    target = owner._snapshot('book', 'first', root)['paths']['provenance']
    store = owner._store
    with monkeypatch.context() as outage:
        def fail(project, root, path, *args, **kwargs):
            if path == target:
                raise OSError('metadata unavailable')
            return store(project, root, path, *args, **kwargs)
        outage.setattr(owner, '_store', fail)
        partial = apply(case, final)
    chapter.write_bytes(b'% Later preamble\n' + chapter.read_bytes())
    physical = chapter.read_bytes()
    payload = partial['reconciliation_read']['payload']
    query = {key: [json.dumps(value) if isinstance(value, (dict, list, bool)) else value]
             for key, value in {'project': 'book', **payload,
                                'current_occurrence_assignments': []}.items()}
    status, _, raw = project_work_surface.handle('/work/structure', query, 'GET', repo_root=root)
    result = json.loads(raw)
    assert status == 200, result
    assert result['metadata_reconciliation']['status'] == 'READY'
    assert result['source_effect'] == partial['source_effect']
    assert chapter.read_bytes() == physical
    for key, bad in [('reconcile_current', 'yes'), ('current_occurrence_assignments', '{}')]:
        status, _, raw = project_work_surface.handle('/work/structure', {**query, key: [bad]}, 'GET', repo_root=root)
        assert status == 422 and key in json.loads(raw)['error']
        assert chapter.read_bytes() == physical
