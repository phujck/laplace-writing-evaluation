"""General writing arrivals retire; explicitly addressed legacy reads stay exact."""
from urllib.parse import parse_qs, urlsplit
import shutil

import pytest

from laplace.web import scanner
from laplace.manuscript import projection_viewer
from test_manuscript_structure import _section_fixture


@pytest.fixture
def entry(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path/'state'))
    monkeypatch.setenv('LAPLACE_SESSION_WORKSPACES', str(tmp_path/'workspaces'))
    _section_fixture(tmp_path)
    monkeypatch.setattr(scanner, '_repo_root', lambda: tmp_path)
    handler_type = scanner.make_handler()

    def get(path):
        # Drive the real route ladder without starting another HTTP service.
        handler = object.__new__(handler_type)
        handler.path = path
        handler.headers = {}
        replies = []
        handler._send = lambda status, body, ctype: replies.append((status, ctype, body))
        handler._redirect = lambda location, code=301: replies.append((code, 'Location', location))
        handler.do_GET()
        assert len(replies) == 1
        return replies[0]

    yield tmp_path, get
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.parametrize('old,expected', [
    ('/', {'workspace':['writing']}),
    ('/?corpus=book', {'corpus':['book'], 'workspace':['writing']}),
    ('/?corpus=book&node=concept%3Afirst', {'corpus':['book'], 'node':['concept:first'], 'workspace':['writing']}),
    ('/artefact', {'workspace':['writing'], 'view':['manuscript']}),
    ('/artefact?corpus=book', {'corpus':['book'], 'workspace':['writing'], 'view':['manuscript']}),
])
def test_general_entry_redirects_to_current_owner_without_losing_root_coordinates(entry, old, expected):
    _, get = entry
    status, kind, location = get(old)
    assert (status, kind) == (301, 'Location')
    target = urlsplit(location)
    assert target.path == '/project' and parse_qs(target.query) == expected


@pytest.mark.parametrize('coordinate', [
    'file=release%2Fr3.pdf', 'version=REL-exact', 'node=concept%3Afirst',
    'object=OBJ-exact', 'finding=FIND-exact', 'mode=read', 'file=', 'unknown=retained',
])
def test_explicit_legacy_coordinate_keeps_legacy_page(entry, coordinate):
    _, get = entry
    status, ctype, page = get('/artefact?corpus=book&'+coordinate)
    assert status == 200 and ctype.startswith('text/html')
    assert b'art-reader' in page


@pytest.mark.parametrize('scope', [
    'corpus=book&corpus=book', 'corpus=book&corpus=other', 'corpus=',
    'corpus=unknown-project', 'corpus=..%2Fbook', 'corpus=%20book', 'corpus=book%00',
])
@pytest.mark.parametrize('path', ['/', '/artefact', '/artefact?file=exact.pdf&'])
def test_bad_scope_refuses_before_redirect_or_legacy_page(entry, path, scope):
    _, get = entry
    status, ctype, body = get(path+('' if '?' in path else '?')+scope)
    assert status == 422 and ctype == 'application/json'
    assert 'scope was not adopted' in body


def test_root_does_not_adopt_conflicting_workspace(entry):
    _, get = entry
    assert get('/?workspace=other')[0] == 422
    assert get('/?workspace=writing&workspace=writing')[0] == 422


def test_projection_owner_duplicate_scope_remains_refused(entry, monkeypatch):
    root, _ = entry
    monkeypatch.setattr(projection_viewer, '_repo_root', lambda: root)
    status, _, _ = projection_viewer.handle('/projection/tex', {
        'corpus':['book','book'], 'view':['source'],
        'file':['synthetics papers/book/manuscript/Fixture-Book.tex']}, 'GET', b'')
    assert status == 422
