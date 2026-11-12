"""Public exact-version handover through existing adapters; no provider or restore."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import runtime_guard

from laplace import sdk
from laplace.native import tools
from laplace.pipeline import workflow as W, workflow_definitions as D
from laplace.projects import library, project_handover as H
from laplace.web import project_work_surface
from laplace.work import object_facets as F, owner_discovery as O

PUBLIC_CATALOGUE = {
    'schema_version': 'laplace.provider-catalogue/1', 'observed_at': 99999999999,
    'providers': [{'id': 'codex', 'available': False, 'models': []}]}


def public_scene(root: Path) -> dict:
    """Supported public owner setup, also usable by the human-route fixture."""
    root.mkdir(parents=True, exist_ok=True)
    (root / 'registry_projects.json').write_text('{"projects": []}')
    cache = root / '.laplace-cache'; cache.mkdir()
    (cache / 'writing-provider-catalogue.json').write_text(json.dumps(PUBLIC_CATALOGUE))
    assert library.create({'name': 'book', 'title': 'Selected public definition',
                           'kind': 'general'}, root)[0] == 201
    body = {'schema_version': D.SCHEMA, 'title': 'Public method v1',
            'description': 'Exact saved instructions and history; no execution.',
            'settings': {}, 'layout': {}, 'edges': [], 'steps': [{
                'id': 'author', 'title': 'Author', 'parent_id': None,
                'assignment': {'role': 'builder', 'instructions':
                               'Preserve Ω / α → β and the complete selected instructions.\n' * 80,
                               'settings': {}}}]}
    versions = []
    for index in (1, 2):
        body = copy.deepcopy(body); body['title'] = f'Public method v{index}'
        versions.append(D.save(root, O.project_scope('book', 'sdk'), {
            'request_id': f'public-save-v{index}', 'expected_revision':
            versions[-1]['version'] if versions else None,
            **({'definition_id': versions[0]['definition_id']} if versions else {}),
            'definition': body}))
    # This is an actual inspected choice; later history reads do not retarget it.
    chosen = F.request(root, O.owned_workspace('http'), {
        'facet': 'object', 'project_lens': 'book', 'reference': versions[1]['reference']})
    body = copy.deepcopy(body); body['title'] = 'Public method v3'
    versions.append(D.save(root, O.project_scope('book', 'sdk'), {
        'request_id': 'public-save-v3', 'definition_id': versions[0]['definition_id'],
        'expected_revision': versions[1]['version'], 'definition': body}))
    return {'root': root, 'versions': versions, 'chosen': chosen}


def http(root, handle, *, extra=None):
    wire = handle['http']; target = urlsplit(wire['url'])
    payload = {**wire.get('payload', {}), **(extra or {})}
    code, _, raw = project_work_surface.handle(
        target.path, parse_qs(target.query), wire['method'],
        json.dumps(payload, ensure_ascii=False).encode() if wire['method'] == 'POST' else b'', root)
    value = json.loads(raw)
    assert code == 200, value
    return value


def three_reads(root, handle):
    """Use each literal owner dialect, without converting a discovery request."""
    return [sdk.workflow_request(handle['request'], root=root),
            tools.execute(root, 'book', 'discuss', handle['native']['operation'],
                          handle['native']['payload']),
            http(root, handle)]


@pytest.fixture
def scene(tmp_path, monkeypatch):
    runtime_guard.arm(monkeypatch)
    monkeypatch.delenv('LAPLACE_CUSTODY_LIVE', raising=False)
    # A recipient intentionally does not copy an origin's .laplace-cache. Keep
    # both homes on the same explicit public metadata instead of probing host cache.
    from laplace.writing import provider_catalogue
    monkeypatch.setattr(provider_catalogue, 'provider_catalogue',
                        lambda *a, **kw: copy.deepcopy(PUBLIC_CATALOGUE))
    return public_scene(tmp_path / 'origin')


def test_exact_old_choice_export_and_offline_ordinary_recipient_across_doors(scene, tmp_path):
    root, versions, chosen = scene['root'], scene['versions'], scene['chosen']
    old = versions[1]; handle = old['read']
    for value in three_reads(root, handle):
        assert value['reference'] == old['reference']
        assert value['definition'] == old['definition']
        assert value['version'] == old['version']
        assert value['head_revision'] == versions[2]['version']
        assert value['currentness'] == 'HISTORICAL'
    entry = chosen['handover_entry']
    assert entry['reference'] == old['reference'] and entry['permit_export'] is False
    prepared = http(root, chosen['handover_prepare'], extra={
        'entries': [{**entry, 'permit_export': True}],
        'max_files': 30, 'max_rows': 30, 'max_bytes': 300000})
    assert prepared['state'] == 'RECORDED'
    included = [e for e in prepared['entries'] if e['class'] == 'included']
    assert len(included) == 1 and included[0]['reference'] == old['reference']
    assert included[0]['currentness'] == 'CURRENT'  # Exact selected basis, not origin head.
    assert included[0]['adapter']['kind'] == 'workflow-definition-editor'
    raw_rows = (root / W.LEDGER).read_bytes().splitlines(keepends=True)
    prefix = [raw for raw in raw_rows if json.loads(raw).get('definition_revision')
              in {versions[0]['version'], old['version']}]
    before = (root / W.LEDGER).read_bytes()
    destination = tmp_path / 'ordinary-recipient'
    exported = http(root, prepared['actions'][0], extra={'destination': str(destination)})
    assert exported['status'] == 'EXPORTED'
    assert (root / W.LEDGER).read_bytes() == before
    assert (destination / W.LEDGER).read_bytes() == b''.join(prefix)
    plan = json.loads((destination / H.MANIFEST).read_bytes())['plan']
    package = plan['workflow_definitions'][0]
    assert [v['row']['definition_revision'] for v in package['versions']] == [
        versions[0]['version'], old['version']]
    for index, version in enumerate(package['versions']):
        assert version['row'] == json.loads(prefix[index])
        assert version['definition'] == versions[index]['definition']
        assert version['row']['receipt'] == versions[index]['receipt']
    # Removing the origin's pathname makes accidental origin fallback observable.
    root.rename(tmp_path / 'offline-origin')
    assert not root.exists()
    seen = H.inspect_handover(destination)
    reopened = sdk.research_handover({'action': 'read', 'reference': prepared['reference']},
                                    root=destination)
    carried = reopened['entries'][0]['frozen_read']
    for value in three_reads(destination, carried):
        assert value['definition'] == old['definition'] and value['reference'] == old['reference']
        assert value['head_revision'] == old['version'] and value['currentness'] == 'CURRENT'
        assert value['pins']['prepared'] == []
    assert seen['providers_started'] == 0
    assert exported['inspection']['origin_reads'] == 0
    (tmp_path / 'consumer-proof.json').write_text(json.dumps({
        'origin_exact_read': old['reference'], 'origin_head': versions[2]['reference'],
        'prepared': prepared, 'exported': exported, 'recipient_read': carried,
        'recipient_inspection': seen, 'exact_original_rows': True,
        'qualification': 'Recipient CURRENT is local head; no origin latestness or runtime grant.'},
        ensure_ascii=False, indent=2))


def test_project_native_scope_and_explicit_share_permission_remain_separate(scene, tmp_path):
    root, chosen = scene['root'], scene['chosen']
    with pytest.raises(D.Refused, match='NOT_IN_SCOPE'):
        tools.execute(root, 'foreign', 'discuss', 'project', {
            'view': 'workflow-definitions', 'request': {'reference': scene['versions'][1]['reference']}})
    payload = {**chosen['handover_prepare']['sdk']['payload'],
               'entries': [chosen['handover_entry']],
               'max_files': 30, 'max_rows': 30, 'max_bytes': 300000}
    ledger = (root / W.LEDGER).read_bytes()
    with pytest.raises(H.Refused, match='EXPLICIT_PERMITTED_ENTRY_REQUIRED'):
        sdk.research_handover(payload, root=root)
    payload['entries'][0] = {**payload['entries'][0], 'permit_export': True}
    with pytest.raises(H.Refused, match='EXPLICIT_AUTHOR_EXPORT_SELECTION_REQUIRED'):
        tools.execute(root, 'book', 'discuss', 'research_handover', payload)
    assert (root / W.LEDGER).read_bytes() == ledger
    assert not (tmp_path / 'recipient').exists()
