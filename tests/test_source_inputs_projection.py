"""Fixed substantive public evaluator for the app-owned source-input reading task.

Run in the selected complete runtime/check-out for independent owner review.
NOT the /usr-only isolated Source.check: no full-source grant/dependency archive
is requested to make imports work. All fixtures below are declared public.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from laplace import sdk, system
from laplace.work import owner_discovery as O, source_contracts as C, source_inventory as I, source_kernel as K

LENS = 'source-as-a-state-structure-impact-and-safe-self-modification'
REFERENCE = {'schema_version': 'laplace.reference/1', 'owner': 'core.identity', 'kind': 'subsystem', 'identity': {'id': 'domain.work'}}


def public_root(tmp_path, *, rich=False):
    root = tmp_path / ('rich' if rich else 'public')
    (root / 'src/laplace/system').mkdir(parents=True)
    (root / 'src/laplace/work').mkdir()
    (root / 'src/public').mkdir()
    (root / 'project').mkdir()
    (root / 'profiles').mkdir()
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [{'name': LENS, 'kind': 'project', 'project_dir': 'project'}]}))
    (root / 'profiles/writing_sources.json').write_text(json.dumps({'repositories': {'public-source': '.'}}))
    # Exactly two public declaring modules, not a source archive or host fixture.
    for provider in C.providers():
        module = __import__(provider.__module__, fromlist=['__file__'])
        relative = Path('src') / Path(provider.__module__.replace('.', '/')).with_suffix('.py')
        (root / relative).write_bytes(Path(module.__file__).read_bytes())
    for n in range(9):
        (root / f'src/public/module_{n:02d}.py').write_text(f'# Public source Ω {n}\nVALUE = {n}\nEXACT_END_{n}\n')
    owner = {'id': 'domain.work', 'kind': 'domain', 'summary': 'Public source inputs',
        'modules': ['laplace.work.project_work_review', 'laplace.work.development_source', 'public.*'],
        'files': [], 'uses': [], 'contracts': [], 'explanation': [], 'evaluators': []}
    # Explicitly large declaration metadata is what inputs projection must defer.
    capabilities = [] if rich else [{'id': f'public-{n}', 'owner': 'domain.work', 'summary': 'Public metadata ' * 50,
        'operation': {'entry': 'not executed; metadata only', 'inputs': [], 'outputs': []}} for n in range(14)]
    description = {'schema_version': system.SCHEMA, 'summary': 'Declared public source fixture', 'subsystems': [owner],
        'capabilities': capabilities, 'distributions': [{'name': 'public', 'declaration': 'pyproject.toml', 'packages': ['laplace', 'public']}]}
    (root / 'src/laplace/system/description.json').write_text(json.dumps(description))
    return root


def http_read(root, handle):
    from laplace.web import project_work_surface
    url = urlsplit(handle['http']['url'])
    code, _, body = project_work_surface.handle(url.path, parse_qs(url.query), 'GET', repo_root=root)
    assert code == 200, body.decode() if isinstance(body, bytes) else body
    return json.loads(body)


def semantic(value):
    return {k: value[k] for k in ('schema_version', 'reference', 'basis', 'items', 'coverage', 'pagination')}


def test_issued_inputs_projection_long_lens_actual_doors_and_exact_body(tmp_path):
    root = public_root(tmp_path)
    chooser = K.read(root, O.project_scope(LENS, 'sdk'), {'facet': 'source-kernel', 'view': 'contracts'})
    selected = next(row for row in chooser['contracts'] if row['reference']['identity']['operation'] == 'work_review.followup')
    issued = selected['inventory_read']
    assert issued['request']['projection'] == 'inputs'
    assert issued['request']['project_lens'] == LENS
    value = http_read(root, issued)
    assert value.get('projection') == 'inputs'
    assert 0 < len(value['items']) <= value['coverage']['requested_limit']
    assert len(json.dumps(value, ensure_ascii=False).encode()) <= 15360 == I.MAX_RESPONSE
    assert value.get('contracts', []) == [] and value.get('capabilities', []) == []
    assert value['coverage']['contract_relations'] == 'NOT_REQUESTED'
    assert value['coverage']['capabilities'] == 'NOT_REQUESTED'
    from laplace.native import tools
    native = tools.execute(root, LENS, 'work', 'project', {'view': 'discovery', 'request': issued['request']})
    python = sdk.request(issued['request'], root=root)
    assert semantic(value) == semantic(native) == semantic(python)
    row = next(r for r in value['items'] if r.get('read', {}).get('http'))
    assert row['sha256'] == 'sha256:' + hashlib.sha256((root / row['path']).read_bytes()).hexdigest()
    from laplace.projects import library, writing_sources
    url = urlsplit(row['read']['http']['url'])
    code, _, body = library.handle(url.path, parse_qs(url.query), 'GET', b'', root)
    assert code == 200, body
    human = json.loads(body)['owner_result']
    exact = writing_sources.execute(root, row['read']['payload'])
    assert human['content'] == exact['content']
    assert row['read']['payload']['expected_sha256'] == row['sha256']


def test_inputs_cut_pages_no_gap_change_refuses_and_legacy_rich_remains(tmp_path):
    root = public_root(tmp_path)
    request = {'facet': 'source-inventory', 'reference': REFERENCE, 'project_lens': LENS, 'projection': 'inputs', 'limit': 2}
    first = O.request(root, O.owned_workspace('sdk'), request)
    seen = []; value = first; count = 0
    while True:
        count += 1; assert count <= 20
        assert value['basis'] == first['basis']
        assert 0 < len(value['items']) <= 2
        assert len(json.dumps(value, ensure_ascii=False).encode()) <= 15360
        seen.extend(r['path'] for r in value['items'])
        next_read = value['pagination']['next_read']
        if not next_read:
            break
        assert next_read['request']['projection'] == 'inputs'
        assert next_read['request']['project_lens'] == LENS
        assert next_read['request']['as_of'] == first['basis']
        assert next_read['request']['offset'] == len(seen)
        value = http_read(root, next_read)
    assert len(seen) == len(set(seen)) == first['coverage']['known']
    old = first['pagination']['next_read']; assert old
    changed = root / first['items'][0]['path']; changed.write_bytes(changed.read_bytes() + b'\n# changed public input\n')
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        O.request(root, O.owned_workspace('sdk'), old['request'])
    rich = I.read(public_root(tmp_path, rich=True), O.owned_workspace('sdk'), {'facet': 'source-inventory', 'reference': REFERENCE, 'limit': 1})
    assert rich.get('projection') != 'inputs' and len(rich['contracts']) == 2
    assert 'segment_bases' in rich['contracts'][0] and 'segment_reads' in rich['contracts'][0]
    assert rich['contracts'][0]['runtime_source_linkage']['state'] == 'UNVERIFIED_LOADED_CODE'


def test_projection_closed_scope_privacy_no_body_fanout(tmp_path, monkeypatch):
    root = public_root(tmp_path)
    request = {'facet': 'source-inventory', 'reference': REFERENCE, 'project_lens': LENS, 'projection': 'inputs'}
    for bad in ['everything', '', 'rich', None, True]:
        with pytest.raises(ValueError):
            O.request(root, O.owned_workspace('sdk'), {**request, 'projection': bad})
    with pytest.raises(ValueError):
        O.request(root, O.project_scope('foreign', 'native'), request)
    with pytest.raises(ValueError):
        O.request(root, O.owned_workspace('sdk'), {**request, 'budget': 1000000})
    private = root / 'src/laplace/pipeline/canon/private.py'; private.parent.mkdir(parents=True); private.write_text('PRIVATE_SENTINEL')
    descriptor = root / 'src/laplace/system/description.json'; description = json.loads(descriptor.read_text())
    description['subsystems'][0]['files'] = ['src/laplace/pipeline/canon/**']; descriptor.write_text(json.dumps(description))
    actual = Path.open
    def guarded(path, *args, **kwargs):
        assert path != private, 'private source body was opened'
        return actual(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)
    from laplace.projects import library
    monkeypatch.setattr(library, 'material_references', lambda *a, **k: pytest.fail('inventory must issue reads, not fetch body windows'))
    value = O.request(root, O.owned_workspace('sdk'), request)
    assert 'PRIVATE_SENTINEL' not in json.dumps(value)
    assert value['state'] == 'PARTIAL' and value['coverage']['unavailable']
