"""Two reached resolution door defects (DD friction diagnosis, M5 2026-10-15).

DD-FRICTION-PART-AVAILABILITY: unresolved resolution metadata advertised a ``current`` text read that could never be
served ("This resolution read has no selected text part") and dropped the owner's guarded preparation action.
DD-FRICTION-HTTP-RESOLUTION-CODEC: GET /authoring/proposal-preview passed the declared object ``target`` as a
string, so a correctly encoded explicit target was refused as "not of type object". Disposable fixtures only.
"""
from __future__ import annotations

import json
from urllib.parse import urlencode, parse_qs

import pytest

from laplace.web import authoring as authoring_surface
from laplace.core import grammar
from laplace.manuscript import proposal_navigation
from laplace.native import tools as writing_tools
from laplace.manuscript import reconciliation
from laplace.core import checkout
from test_human_reconciliation import current_candidate, target  # noqa: F401  (the retained fixture)


def _native(root, selector, request):
    result = writing_tools.call(root, 'fixture', 'revise', request, turn_id=selector['turn_id'])
    assert result['ok'], result
    return result['owner_response']


def test_unresolved_metadata_offers_only_real_parts_and_keeps_the_owner_preparation_route(current_candidate):
    root, md, source, selector = current_candidate
    (md / 'main.tex').write_text((md / 'main.tex').read_text().replace('Green', 'Violet'))
    metadata = _native(root, selector, reconciliation.action('fixture', 'prepare-resolution', selector)['native_request'])
    assert metadata['target_required'] and metadata['source_currentness'] == 'UNRESOLVED'
    assert set(metadata['text_reads']) == {'original', 'proposed'}, 'no current door without current text'
    original = _native(root, selector, metadata['text_reads']['original']['native_request'])
    assert original['content'].startswith('Red statement.')
    action = metadata['resolution_action']
    assert action['operation'] == 'authoring/proposal-decision' and action['native_request']['payload']['view'] == 'resolution'
    # the kept route plus an explicitly inspected current target yields a real current part
    explicit = reconciliation.action('fixture', 'prepare-resolution', {**selector, 'target': target(root, md, source)})['native_request']
    assert 'edge_target' in explicit['payload'], 'the owner target rides the grammar carrier'
    resolved = _native(root, selector, explicit)
    assert not resolved['target_required'] and 'current' in resolved['text_reads']
    current = _native(root, selector, resolved['text_reads']['current']['native_request'])
    assert 'Violet statement.' in current['content']


def _http(root, monkeypatch, query):
    monkeypatch.setattr(checkout, 'repo_root', lambda: root)
    status, _, body = authoring_surface.handle('/authoring/proposal-preview', parse_qs(urlencode(query)), 'GET', b'')
    return status, json.loads(body)


def test_http_resolution_get_decodes_the_declared_object_target(current_candidate, monkeypatch):
    root, md, source, selector = current_candidate
    (md / 'main.tex').write_text((md / 'main.tex').read_text().replace('Green', 'Violet'))
    query = {'project': 'fixture', 'id': selector['turn_id'], 'proposal_version': selector['proposal_version'],
             'edit_id': selector['edit_id'], 'view': 'resolution', 'target': json.dumps(target(root, md, source))}
    status, value = _http(root, monkeypatch, query)
    assert status == 200, value
    assert value['target_required'] is False and value['target']['before'].startswith('Red statement.')


@pytest.mark.parametrize('field,raw', [('target', '{"file": '), ('target', '[1, 2]'), ('choices', '{"a": 1}'), ('hunk_offset', '-3')])
def test_malformed_typed_query_values_refuse_before_the_owner(current_candidate, monkeypatch, field, raw):
    root, md, source, selector = current_candidate
    monkeypatch.setattr(proposal_navigation, 'read', lambda *a, **k: pytest.fail('the owner was reached'))
    query = {'project': 'fixture', 'id': selector['turn_id'], 'proposal_version': selector['proposal_version'],
             'edit_id': selector['edit_id'], 'view': 'resolution', field: raw}
    status, value = _http(root, monkeypatch, query)
    assert status >= 400 and field in json.dumps(value)
