"""Owner discovery (work.owner-discovery, P0a): a caller starts at the system entry and reaches canonical Work.

Every case runs the real owners over a synthetic workspace: the Work ledger and its writer (project_work), the
detail projection (project_work_views), qualified activity through its human attestation door
(project_work_activity), the HTTP door (project_work_surface) and the native operation door
(writing.operations). The fixture mirrors the public ids, titles and kinds of the two reached campaigns (the
development campaign with its hardening Work and the completed physical programme; the Living Guide documentation
campaign with its unbound current-edition child); goals and evidence are synthetic.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from laplace import sdk, system
from laplace.core import identity
from laplace.work import owner_discovery as od
from laplace.work import project_work as w
from laplace.work import project_work_activity as activity

NS_A = 'writing-system-architecture'
NS_B = 'source-as-a-state-structure-impact-and-safe-self-modification'
NS_C = 'synthetic-private-notes'
JOINS, GUIDE = 'WORK-writing-joins-codex-20261006', 'WORK-living-blueprint-20261004'
EDITION, HARDEN = 'WORK-guide-current-edition-20261009', 'WORK-frontend-interaction-hardening-20261021'
PROGRAMME, PRIVATE = 'WORK-15f85c944eb341e5aaf927527cff98df', 'WORK-private-synthetic'
PRIVATE_TITLE = 'Private synthetic draft title'
TASK = 'find current work affecting the browser/workflow interface'
SRC = Path(__file__).resolve().parents[1] / 'src' / 'laplace'
PROGRAMME_EVIDENCE = 'projects/source-state/evidence/programme.md'
OUTSIDE_EVIDENCE = 'evidence/outside.json'
EVIDENCE_TOTAL = 7


def sub(ident):
    return identity.reference('core.identity', 'subsystem', {'id': ident})


def bind(root, namespace, ident, relations, **extra):
    current = od.current_binding(root, namespace, ident)
    payload = {'namespace': namespace, 'id': ident, 'expected_work_revision': w._task_revision(w._tasks(namespace, root)[ident]),
               'expected_binding_revision': current['binding_revision'] if current else None,
               'relations': [{'relation': relation, 'target': target} for relation, target in relations], **extra}
    return sdk.bind(payload, root=root)


ADOPTION = lambda: [   # the two reached campaign associations, as the Work owner records them (no other mapping)
    (NS_A, JOINS, [('coordinates', sub('core.identity')), ('coordinates', sub('adapter.http')), ('coordinates', sub('adapter.desktop')),
                   ('coordinates', sub('domain.work')), ('coordinates', od.work_reference(NS_B, PROGRAMME)),
                   ('coordinates', od.work_reference(NS_A, HARDEN))]),
    (NS_A, HARDEN, [('targets', sub('adapter.http')), ('targets', sub('adapter.desktop')), ('targets', sub('domain.pipeline')),
                    ('targets', sub('domain.work'))]),
    (NS_A, GUIDE, [('explains', sub('adapter.explanation')), ('consumes', od.work_reference(NS_A, JOINS))]),
    (NS_B, PROGRAMME, [('targets', sub('core.runtime')), ('targets', sub('core.identity')), ('targets', sub('adapter.distribution'))]),
    (NS_C, PRIVATE, [('targets', sub('adapter.http')), ('targets', sub('adapter.desktop'))])]


def observe(root, namespace, ident, state, observed, expires, request_id):
    scope = w._work_basis(w._tasks(namespace, root), ident)[0]['scope_revision']
    return activity.record(namespace, {
        'id': ident, 'request_id': request_id, 'subject': {'kind': 'external-actor', 'actor': 'Sol coordinator', 'session_id': 'synthetic-1'},
        'observed_state': state, 'observed_at': observed.isoformat(), 'expires_at': expires.isoformat(),
        'consumed_scope_revision': scope, 'observer': 'synthetic coordinator status read', 'source': 'fixture actor-status read',
        'evidence_absent': 'synthetic fixture'}, root, door={'origin': 'human'})


def disposition(root, namespace, ident, status, evidence=()):
    guard = w.read(namespace, {'view': 'detail', 'id': ident}, root)['allowed_actions']['task_status']['payload']
    return w.transition(namespace, {**guard, 'status': status, **({'evidence': list(evidence)} if evidence else {})}, root)


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / 'workspace'
    (root / 'contract').mkdir(parents=True)
    # the two campaign namespaces are registered projects with artifact homes (the private one stays unregistered)
    homes = {NS_A: 'projects/architecture', NS_B: 'projects/source-state'}
    for home in homes.values():
        (root / home / 'manuscript').mkdir(parents=True)
        (root / home / 'manuscript' / 'main.tex').write_text('\\documentclass{article}\\begin{document}x\\end{document}\n')
        (root / home / 'evidence').mkdir()
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [
        {'name': name, 'kind': 'conceptric', 'project_dir': home, 'tex_root': home + '/manuscript/main.tex'} for name, home in homes.items()]}))
    def make(namespace, ident, title, **fields):
        w.task(namespace, {'id': ident, 'title': title, 'goal': 'Synthetic goal: ' + title, **fields}, root)
    make(NS_A, JOINS, 'Reconcile the Laplace engine, its interfaces and living guide', kind='campaign')
    make(NS_A, GUIDE, 'Maintain the living system guide through reconciliation', kind='documentation')
    make(NS_A, EDITION, 'Rebuild the current Living System Guide for a new reader', kind='documentation', parent_work_id=GUIDE)
    hardening_evidence = []
    for n in range(EVIDENCE_TOTAL):   # more than one page of evidence reads, each inside the project's artifact home
        path = homes[NS_A] + '/evidence/design-%d.md' % n
        (root / path).write_text('Design evidence %d\n' % n)
        hardening_evidence.append(path)
    make(NS_A, HARDEN, 'Harden the shared interaction and configuration design',   # not a child of the campaign (as observed)
         evidence=hardening_evidence)
    make(NS_B, PROGRAMME, 'Organise the owned system into one coherent implementation tree', kind='programme')
    make(NS_C, PRIVATE, PRIVATE_TITLE)
    (root / PROGRAMME_EVIDENCE).write_text('R1-R5 physical programme: done\n')
    (root / 'evidence').mkdir()
    (root / OUTSIDE_EVIDENCE).write_text('{"retained": "outside any project artifact home"}')
    for namespace, ident in ((NS_A, JOINS), (NS_A, GUIDE), (NS_A, HARDEN)):
        disposition(root, namespace, ident, 'in-progress')
    disposition(root, NS_B, PROGRAMME, 'done', [PROGRAMME_EVIDENCE, OUTSIDE_EVIDENCE])
    now = dt.datetime.now(dt.timezone.utc)
    observe(root, NS_A, HARDEN, 'running', now - dt.timedelta(minutes=1), now + dt.timedelta(hours=1), 'req-hardening-0001')
    observe(root, NS_B, PROGRAMME, 'running', now - dt.timedelta(hours=3), now - dt.timedelta(hours=2), 'req-programme-0001')
    for namespace, ident, relations in ADOPTION():
        bind(root, namespace, ident, relations, by='fixture owner adoption')
    return root


def http(root, url, method='GET', body=None):
    """The real HTTP owner of the path (/work/* or /research/*); a non-JSON body reads as {'content': text}, as the
    app's transport does."""
    from laplace.web import project_work_surface, research_surface
    parts = urlsplit(url)
    owner = research_surface if parts.path.startswith('/research/') else project_work_surface
    code, kind, raw = owner.handle(parts.path, parse_qs(parts.query), method,
                                   json.dumps(body).encode() if body is not None else b'', repo_root=root)
    return code, (json.loads(raw) if 'json' in kind else {'content': raw.decode('utf-8')})


def native(root, namespace, request):
    from laplace.writing import operations
    return operations._execute(root, namespace, 'work', 'project', {'view': 'discovery', 'request': request})


def strip_scope(value):
    return {key: item for key, item in json.loads(json.dumps(value)).items() if key != 'scope'}


def minted_request_ids(value):
    """Request identities an owner action itself declares outside its intent (intent_projection.excluded_fields)."""
    found = set()
    def walk(node):
        if isinstance(node, dict):
            excluded = (node.get('intent_projection') or {}).get('excluded_fields') or []
            for carrier in (node.get('payload'), (node.get('http') or {}).get('payload')):
                if isinstance(carrier, dict):
                    found.update(carrier[field] for field in excluded if isinstance(carrier.get(field), str))
            for item in node.values():
                walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(json.loads(json.dumps(value)))
    return found


def owner_intent(value):
    """Owner facts compared by intent: only values an action's own intent_projection excludes are masked."""
    text = json.dumps(value, sort_keys=True)
    for token in sorted(minted_request_ids(value), key=len, reverse=True):
        text = text.replace(json.dumps(token)[1:-1], '<owner-excluded-request-id>')
    return json.loads(text)


# --------------------------------------------------------------------------------------------- fresh entry
def test_a_fresh_caller_reaches_the_same_canonical_work_from_the_system_entry_alone(workspace):
    """Given only the system entry, the task and its scope, the caller follows returned handles: owner choices ->
    affecting Work -> canonical Work with actor/state/next/blockers and evidence -> up-summary -> lateral campaigns."""
    entry = sdk.describe(task=TASK, root=workspace)
    assert entry['schema_version'] == od.RESULT_SCHEMA and entry['grade'] == 'system'
    choices = entry['selection']['choices']
    chosen = next(choice for choice in choices if 'browser' in choice['terms'])   # the caller's own choice, by meaning
    assert len(choices) >= 2 and 'Nothing was selected for you' in entry['selection']['says']
    page = sdk.request(chosen['next']['request'], root=workspace)
    assert page['grade'] == 'subsystem' and page['coverage']['unbound'] == od.UNBOUND
    titles = {item['title']: item for item in page['items']}
    assert 'Harden the shared interaction and configuration design' in titles
    assert 'Reconcile the Laplace engine, its interfaces and living guide' in titles
    assert PRIVATE_TITLE in titles   # the owned workspace reads every namespace it holds
    hardening = sdk.request(titles['Harden the shared interaction and configuration design']['next']['request'], root=workspace)
    assert hardening['reference']['identity'] == {'namespace': NS_A, 'id': HARDEN}
    assert hardening['legacy']['qualified_id'] == NS_A + '::' + HARDEN
    assert hardening['standing']['status'] == 'in-progress'
    assert hardening['activity']['state'] == 'running'
    assert hardening['activity']['observations'][0]['subject']['actor'] == 'Sol coordinator'
    assert {action['name'] for action in hardening['next']['actions']} >= {'task', 'task_status'}
    assert hardening['read_cut']['binding_revision'] == od.current_binding(workspace, NS_A, HARDEN)['binding_revision']
    assert {item['reference']['identity']['id'] for item in hardening['up']} == {'adapter.http', 'adapter.desktop', 'domain.pipeline', 'domain.work'}
    # up: the subsystem's summary, then the system entry, through returned handles only
    up = sdk.request(page['up_summary']['up']['request'], root=workspace)
    assert up['facet'] == 'describe' and 'affect adapter.desktop' in page['up_summary']['says']
    # lateral: the campaign that coordinates it (an incoming relation), then that campaign's coordinated programme in
    # another namespace and the guide that consumes it
    campaign = sdk.request(next(item for item in hardening['lateral'] if item.get('direction') == 'incoming' and item['relation'] == 'coordinates')['next']['request'], root=workspace)
    assert campaign['title'] == 'Reconcile the Laplace engine, its interfaces and living guide' and campaign['task_kind'] == 'campaign'
    lateral = {(item['relation'], item.get('direction'), item['title']) for item in campaign['lateral']}
    assert ('coordinates', 'outgoing', 'Organise the owned system into one coherent implementation tree') in lateral
    assert ('consumes', 'incoming', 'Maintain the living system guide through reconciliation') in lateral
    programme = sdk.request(next(item for item in campaign['lateral'] if item['reference']['identity'].get('id') == PROGRAMME)['next']['request'], root=workspace)
    assert programme['standing']['status'] == 'done' and programme['evidence']['items'][0]['path'] == PROGRAMME_EVIDENCE
    code, read = http(workspace, programme['evidence']['items'][0]['http']['url'])   # the selected evidence, through its owner
    assert code == 200 and read['content'] == 'R1-R5 physical programme: done\n'
    guide = sdk.request(next(item for item in campaign['lateral'] if item.get('direction') == 'incoming')['next']['request'], root=workspace)
    assert guide['title'] == 'Maintain the living system guide through reconciliation'
    assert guide['coverage']['children'] == 1   # the unbound current-edition child is counted by its parent, not invented


def test_native_and_http_doors_return_the_sdk_owner_facts(workspace):
    entry = sdk.describe(task=TASK, root=workspace)
    code, over_http = http(workspace, entry['selection']['choices'][0]['next']['http']['url'])
    assert code == 200
    assert strip_scope(over_http) == strip_scope(sdk.request(entry['selection']['choices'][0]['next']['request'], root=workspace))
    request = {'facet': 'inspect', 'reference': od.work_reference(NS_A, HARDEN)}
    by_sdk = sdk.request(request, root=workspace)
    code, by_http = http(workspace, od.handle(request)['http']['url'])
    by_native = native(workspace, NS_A, request)
    # each door returns the same owner facts; a planning request identity is minted per read and declared outside intent
    assert code == 200 and owner_intent(strip_scope(by_http)) == owner_intent(strip_scope(by_sdk))
    assert owner_intent({key: by_native[key] for key in by_sdk if key != 'scope'}) == owner_intent(strip_scope(by_sdk))
    minted = [minted_request_ids(view) for view in (by_sdk, by_http, by_native)]
    assert all(minted) and minted[0].isdisjoint(minted[1]) and minted[0].isdisjoint(minted[2])
    assert by_native['scope'] == {'kind': 'project', 'door': 'native', 'namespace': NS_A, 'says': by_native['scope']['says']}
    assert by_http['scope']['door'] == 'http' and by_sdk['scope']['door'] == 'sdk'
    # the native handle the owner returns is the existing Work read, with the same request inside it
    assert od.handle(request)['native'] == {'operation': 'project', 'payload': {'view': 'discovery', 'request': request}}


# --------------------------------------------------------------------------------------------- identity and custody
def test_binding_is_guarded_idempotent_and_moves_no_work_revision_or_read_cut(workspace):
    ledger = w._ledger(workspace)
    read = lambda: w.read(NS_A, {'view': 'detail', 'id': GUIDE}, workspace)
    before = read()
    pins = ('work_revision', 'work_scope_revision', 'work_status_revision', 'dependency_revision', 'status')
    current = od.current_binding(workspace, NS_A, GUIDE)
    relations = [('explains', sub('adapter.explanation')), ('consumes', od.work_reference(NS_A, JOINS)), ('explains', sub('core.identity'))]
    changed = bind(workspace, NS_A, GUIDE, relations)
    assert changed['replayed'] is False and changed['owned_changes']['objects'][0]['owner'] == 'project-work'
    assert changed['binding']['prior_binding_revision'] == current['binding_revision'] and changed['binding']['history'] == 2
    after = read()
    assert after['read_cut'] == before['read_cut']
    assert {key: after['task'][key] for key in pins} == {key: before['task'][key] for key in pins}
    lines = ledger.read_bytes()
    # replay of the request that is already current: same result, no new row
    replay = sdk.bind({'namespace': NS_A, 'id': GUIDE, 'expected_work_revision': before['task']['work_revision'],
                       'expected_binding_revision': current['binding_revision'],
                       'relations': [{'relation': r, 'target': t} for r, t in relations]}, root=workspace)
    assert replay['replayed'] is True and replay['binding'] == changed['binding'] and ledger.read_bytes() == lines
    # a stale binding guard: zero effect, the current binding stays
    with pytest.raises(w.WorkConflict) as stale_binding:
        sdk.bind({'namespace': NS_A, 'id': GUIDE, 'expected_work_revision': before['task']['work_revision'],
                  'expected_binding_revision': current['binding_revision'],
                  'relations': [{'relation': 'explains', 'target': sub('domain.work')}]}, root=workspace)
    assert stale_binding.value.details['field'] == 'expected_binding_revision' and ledger.read_bytes() == lines
    # a stale specification guard after an owner edit of the Work: zero effect
    w.task(NS_A, {'id': GUIDE, 'title': 'Maintain the living system guide', 'expected_work_revision': before['task']['work_revision']}, workspace)
    lines = ledger.read_bytes()
    with pytest.raises(w.WorkConflict) as stale_spec:
        sdk.bind({'namespace': NS_A, 'id': GUIDE, 'expected_work_revision': before['task']['work_revision'],
                  'expected_binding_revision': changed['binding']['binding_revision'],
                  'relations': [{'relation': 'explains', 'target': sub('domain.work')}]}, root=workspace)
    assert stale_spec.value.details['field'] == 'expected_work_revision' and ledger.read_bytes() == lines
    assert od.current_binding(workspace, NS_A, GUIDE) == changed['binding']
    # the in-lock comparison: a refusal raised by the admission appends nothing
    def refuse():
        raise w.WorkConflict('moved', NS_A, GUIDE)
    with pytest.raises(w.WorkConflict):
        w._append(workspace, {'record': od.BINDING_RECORD, 'id': 'BIND-never', 'project': NS_A, 'work_id': GUIDE}, admit=refuse)
    assert ledger.read_bytes() == lines


def test_old_and_new_handles_resolve_to_one_work_and_a_bare_id_offers_choices(workspace):
    detail = w.read(NS_A, {'view': 'detail', 'id': JOINS}, workspace)
    canonical = od.work_reference(NS_A, JOINS)
    for value in (NS_A + '::' + JOINS, detail['task']['read_handle'], canonical, detail['read_handles'][0]):
        resolved = sdk.resolve(value, root=workspace)
        assert resolved['status'] == 'RESOLVED' and resolved['reference'] == canonical, value
        assert sdk.request(resolved['next']['request'], root=workspace)['title'] == detail['task']['title']
    # the legacy detail read still answers through the old route, byte-for-byte the same Work
    code, old = http(workspace, detail['task']['read_handle']['http']['url'])
    assert code == 200 and old['task']['id'] == JOINS and old['task']['work_revision'] == detail['task']['work_revision']
    # a local id held by two namespaces is never guessed
    w.task(NS_C, {'id': JOINS, 'title': 'A different Work with the same local id', 'goal': 'Synthetic collision'}, workspace)
    ambiguous = sdk.resolve(JOINS, root=workspace)
    assert ambiguous['status'] == 'AMBIGUOUS' and {c['reference']['identity']['namespace'] for c in ambiguous['choices']} == {NS_A, NS_C}
    confined = od.request(workspace, od.project_scope(NS_A, 'native'), {'facet': 'resolve', 'reference': JOINS})
    assert confined['status'] == 'RESOLVED' and confined['reference']['identity']['namespace'] == NS_A
    assert sdk.resolve('WORK-absent', root=workspace)['status'] == 'NOT_IN_SCOPE'


# --------------------------------------------------------------------------------------------- scoped negative/partial
def test_a_project_confined_caller_sees_no_foreign_title_id_or_count(workspace):
    owned = sdk.describe(root=workspace)
    owned_http = next(item for item in owned['subsystems'] if item['reference']['identity']['id'] == 'adapter.http')
    confined = native(workspace, NS_A, {'facet': 'describe'})
    confined_http = next(item for item in confined['subsystems'] if item['reference']['identity']['id'] == 'adapter.http')
    assert owned_http['affecting_work']['bound_in_scope'] == 3 and confined_http['affecting_work']['bound_in_scope'] == 2
    page = native(workspace, NS_A, {'facet': 'discover', 'subsystem': 'adapter.http'})
    campaign = native(workspace, NS_A, {'facet': 'inspect', 'reference': od.work_reference(NS_A, JOINS)})
    assert campaign['coverage']['withheld'] and all(item['reference']['identity'].get('id') != PROGRAMME for item in campaign['lateral'])
    text = json.dumps([confined, page, campaign])
    for foreign in (PRIVATE_TITLE, PRIVATE, NS_C, NS_B, PROGRAMME, 'Organise the owned system'):
        assert foreign not in text, foreign
    # out of scope and absent refuse alike, through every door
    from laplace.writing.operations import _execute
    refusals = []
    for target in (od.work_reference(NS_C, PRIVATE), od.work_reference(NS_A, 'WORK-absent')):
        with pytest.raises(od.DiscoveryRefusal) as refused:
            native(workspace, NS_A, {'facet': 'inspect', 'reference': target})
        refusals.append((refused.value.details, str(refused.value)))
    assert refusals[0] == refusals[1] and refusals[0][0]['code'] == 'NOT_IN_SCOPE'
    assert native(workspace, NS_A, {'facet': 'resolve', 'reference': NS_C + '::' + PRIVATE})['status'] == 'NOT_IN_SCOPE'
    # a project field in the native payload never widens the scope
    with pytest.raises(ValueError):
        _execute(workspace, NS_A, 'work', 'project', {'view': 'discovery', 'request': {'facet': 'describe'}, 'project': NS_C})


def test_unknown_unsupported_and_ambiguous_targets_return_typed_local_results(workspace):
    def code_of(relations, ident=HARDEN):
        with pytest.raises(od.DiscoveryRefusal) as refused:
            bind(workspace, NS_A, ident, relations)
        return refused.value.details['code']
    lines = w._ledger(workspace).read_bytes()
    assert code_of([('targets', sub('adapter.nowhere'))]) == 'UNKNOWN_TARGET'
    assert code_of([('targets', identity.reference('domain.manuscript', 'document', {'id': 'living-guide'}))]) == 'UNSUPPORTED_TARGET'
    assert code_of([('responsible-owner', od.work_reference(NS_A, JOINS))]) == 'UNSUPPORTED_TARGET'
    assert code_of([('targets', od.work_reference(NS_A, HARDEN))]) == 'UNSUPPORTED_TARGET'
    assert code_of([('targets', od.work_reference(NS_A, 'WORK-absent'))]) == 'NOT_IN_SCOPE'
    assert code_of([('targets', sub('adapter.http')), ('targets', sub('adapter.http'))]) == 'DUPLICATE_RELATION'
    assert code_of([('targets', {'owner': 'core.identity', 'kind': 'subsystem'})]) == 'MALFORMED_REFERENCE'
    assert w._ledger(workspace).read_bytes() == lines
    with pytest.raises(od.DiscoveryRefusal) as unknown:
        sdk.discover('adapter.nowhere', root=workspace)
    assert unknown.value.details['code'] == 'UNKNOWN_SUBSYSTEM' and unknown.value.details['next_reads'][0]['request'] == {'facet': 'describe'}
    nothing = sdk.describe(task='zzzz qqqq', root=workspace)['selection']
    assert nothing['choices'] == [] and 'No declared subsystem word' in nothing['says']
    code, body = http(workspace, '/work/discovery?facet=discover&subsystem=adapter.nowhere')
    assert code == 422 and body['code'] == 'UNKNOWN_SUBSYSTEM'
    code, body = http(workspace, '/work/binding', 'POST', {'namespace': NS_A, 'id': HARDEN, 'expected_work_revision': 'sha256:' + '0' * 64,
                                                             'expected_binding_revision': None, 'relations': [{'relation': 'targets', 'target': sub('adapter.http')}]})
    assert code == 409 and body['code'] == 'CHANGED_INPUT'


def test_expired_activity_reads_unknown_and_an_independent_neighbour_stays_current(workspace):
    programme = sdk.inspect(od.work_reference(NS_B, PROGRAMME), root=workspace)
    assert programme['activity']['state'] == 'unknown' and programme['activity']['qualification'].startswith('UNKNOWN now')
    assert programme['activity']['observations'][0]['current'] is False
    accepted = programme['standing']['current_acceptance']
    before = w.read(NS_B, {'view': 'detail', 'id': PROGRAMME}, workspace)['read_cut']
    # binding, observing and editing other Work leave the completed programme's acceptance and read cut current
    bind(workspace, NS_A, HARDEN, [('targets', sub('adapter.http'))])
    w.task(NS_A, {'id': JOINS, 'title': 'Reconcile the engine', 'expected_work_revision': w._task_revision(w._tasks(NS_A, workspace)[JOINS])}, workspace)
    again = sdk.inspect(od.work_reference(NS_B, PROGRAMME), root=workspace)
    assert again['standing']['current_acceptance'] == accepted and accepted['status'] == 'CURRENT'
    assert w.read(NS_B, {'view': 'detail', 'id': PROGRAMME}, workspace)['read_cut'] == before


def test_a_truncated_page_continues_and_a_changed_binding_refuses_the_old_cut(workspace):
    for n in range(4):
        w.task(NS_A, {'id': 'WORK-extra-%d' % n, 'title': 'Extra Work %d' % n, 'goal': 'Synthetic'}, workspace)
        bind(workspace, NS_A, 'WORK-extra-%d' % n, [('targets', sub('domain.work'))])
    first = sdk.discover('domain.work', limit=2, root=workspace)
    assert first['total'] == 6 and len(first['items']) == 2 and first['coverage']['truncated'] is True
    second = sdk.request(first['next']['request'], root=workspace)
    assert second['offset'] == 2 and not {i['title'] for i in second['items']} & {i['title'] for i in first['items']}
    bind(workspace, NS_A, 'WORK-extra-0', [('targets', sub('domain.work')), ('consumes', od.work_reference(NS_A, JOINS))])
    with pytest.raises(od.DiscoveryRefusal) as moved:
        sdk.request(first['next']['request'], root=workspace)
    assert moved.value.details['code'] == 'CHANGED_INPUT'
    assert sdk.request(moved.value.details['next_reads'][0]['request'], root=workspace)['total'] == 6


# --------------------------------------------------------------------------------------------- layers and packaging
def test_the_system_entry_is_structural_and_the_sdk_is_a_declared_adapter():
    def imported(path):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        return {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module} | \
               {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    for core in (SRC / 'system' / '__init__.py', SRC / 'core' / 'identity.py'):
        assert not {name for name in imported(core) if name.startswith(('laplace.work', 'laplace.web', 'laplace.native', 'laplace.sdk', 'laplace.writing'))}
    description = system.load()
    assert system.owner(description, 'src/laplace/sdk.py')[0] == 'adapter.sdk'
    assert system.owner(description, 'src/laplace/work/owner_discovery.py')[0] == 'domain.work'
    assert system.capability('work.owner-discovery', description)['problems'] == []
    root = SRC.parents[1]
    measured = system.graph(root)
    family = {'laplace.sdk', 'laplace.work.owner_discovery', 'laplace.system', 'laplace.core.identity', 'laplace.work.project_work_views'}
    retained = {tuple(edge) for row in description['retained'] for edge in row['edges']}   # declared, pre-existing
    bad = [row for row in system.violations(description, measured) if row[0] in family and row[:2] not in retained]
    assert bad == [], bad
    entry = system.entry(description)
    assert {'capability', 'subsystem'} == {row['reference']['kind'] for row in entry['subsystems'] + entry['capabilities']}
    assert any(row['reference']['identity']['id'] == 'work.owner-discovery' for row in entry['capabilities'])
    from laplace.web import shared_ui
    snapshot = shared_ui.capture_asset_snapshot()
    assert 'workspace-owners.mjs' in snapshot.assets
    assert b"import('/shared/workspace-owners.mjs')" in snapshot.assets['project-work.mjs'][1]


# --------------------------------------------------------------------------------------------- the human route
def test_the_owners_view_replies_come_from_the_real_http_door(workspace, tmp_path):
    """The browser case's input: every reply the System owners view requests, with its HTTP status, served by the
    real owners (/work/discovery and the evidence owner /research/artifact) over this workspace; then the same
    evidence read after its pinned bytes changed. The node case (tests/owner_discovery_frontend.test.mjs) paints
    exactly these bytes."""
    import os
    from urllib.parse import urlencode
    replies, changed = {}, {}
    def get(url, into=replies):
        code, value = http(workspace, url)
        into[url] = {'code': code, 'value': value}
        assert code == 200 or into is changed, value
        return value
    get('/work/discovery?facet=describe')
    asked = get('/work/discovery?' + urlencode({'facet': 'describe', 'task': TASK}))
    chosen = next(choice for choice in asked['selection']['choices'] if 'browser' in choice['terms'])
    page = get(chosen['next']['http']['url'])
    hardening = get(next(item for item in page['items'] if item['reference']['identity']['id'] == HARDEN)['next']['http']['url'])
    campaign = get(next(item for item in hardening['lateral'] if item.get('direction') == 'incoming')['next']['http']['url'])
    programme = get(next(item for item in campaign['lateral'] if item['reference']['identity'].get('id') == PROGRAMME)['next']['http']['url'])
    get(page['up_summary']['up']['http']['url'])
    evidence = programme['evidence']['items'][0]['http']['url']
    assert get(evidence)['content'] == 'R1-R5 physical programme: done\n'
    (workspace / PROGRAMME_EVIDENCE).write_text('Changed after completion\n')
    refused = get(evidence, changed)
    assert changed[evidence]['code'] == 409 and refused.get('error')
    # genuine qualified Source-input pages: the inventory owner's own cut over CRLF and non-BMP text, paged in Unicode scalars
    from test_source_owner_inventory import fixture as source_fixture
    from laplace.web import project_work_surface
    from laplace.writing import operations
    source_root, reference = source_fixture(tmp_path / 'source-owner')
    guide = '# Public source guide π\U0001F331\r\n\r\n| A | B |\r\n|---|---|\r\n' + ''.join('| \U0001F331 %d | é |\r\n' % n for n in range(12))
    (source_root / 'docs/public.md').write_bytes(guide.encode('utf-8'))
    def door(url):
        parts = urlsplit(url)
        code, _, raw = project_work_surface.handle(parts.path, parse_qs(parts.query), 'GET', repo_root=source_root)
        assert code == 200, raw
        return json.loads(raw)
    inventory = door('/work/discovery?' + urlencode({'facet': 'source-inventory', 'reference': json.dumps(reference), 'projection': 'inputs'}))
    row = next(item for item in inventory['items'] if item['path'] == 'docs/public.md')
    parts = urlsplit(row['read']['workspace_read']['http']['url'])
    source_first = parts.path + '?' + urlencode({**{key: values[0] for key, values in parse_qs(parts.query).items()}, 'limit': 64})
    source_pages, url = {}, source_first
    while url:
        page = door(url)
        source_pages[url] = page
        url = ((page['pagination'].get('next_read') or {}).get('http') or {}).get('url')
        if url:
            assert page['next_offset'] == page['offset'] + len(page['content'])
    assert len(source_pages) >= 2 and len({page['units'] for page in source_pages.values()}) == 1
    assert ''.join(page['content'] for page in source_pages.values()) == guide.replace('\r\n', '\n')
    # genuine Artifact owner pages: UTF-8 byte offsets, size_bytes and terminal fields over CRLF and non-BMP text
    artifact_text = '# Artifact π\U0001F331\r\n\r\n| A | B |\r\n|---|---|\r\n' + ''.join('| \U0001F331 %d | é |\r\n' % n for n in range(8))
    (workspace / 'projects/architecture/evidence/reading.md').write_bytes(artifact_text.encode('utf-8'))
    # through the library Material owner's own Artifact preview, following only the wrapper's issued continuation
    from laplace.projects import library
    target = {'owner': 'artifact', 'project': NS_A, 'path': 'evidence/reading.md', 'scope': 'project'}
    page = library.material_references(NS_A, workspace, view='preview', target=target, offset=0, limit=48)
    material_first = '/material/first'
    artifact_pages, key, contents = {}, material_first, []
    while True:
        artifact_pages[key] = json.loads(json.dumps(page))
        result = page.get('owner_result') or page
        contents.append(result['content'])
        handle = page.get('read_handle')
        if not handle:
            break
        assert handle['http']['method'] == 'GET' and result['next_offset'] == result['offset'] + len(result['content'].encode('utf-8'))
        payload = {name: value for name, value in (handle.get('payload') or {}).items() if name != 'project'}
        key = handle['http']['url']
        page = library.material_references(NS_A, workspace, **payload)
    assert len(artifact_pages) >= 2 and result['complete'] is True and result['next_offset'] is None
    assert result['offset'] + len(result['content'].encode('utf-8')) == result['size_bytes'] == len(artifact_text.encode('utf-8'))
    assert ''.join(contents) == artifact_text
    out = Path(os.environ.get('TMPDIR') or tmp_path).parent / 'owner-discovery-replies.json'
    out.write_text(json.dumps({'task': TASK, 'replies': replies, 'changed': changed, 'evidence': evidence, 'source_first': source_first,
                               'source_pages': source_pages, 'material_first': material_first, 'artifact_pages': artifact_pages}, sort_keys=True), encoding='utf-8')
    assert json.loads(out.read_text())['replies'][chosen['next']['http']['url']]['value']['subsystem']['reference']['identity']['id'] == 'adapter.desktop'


# --------------------------------------------------------------------------------------------- correction: P0-R1 / P0-R2
def _work_ref(**override):
    value = {'schema_version': identity.REFERENCE_SCHEMA, 'owner': 'domain.work', 'kind': 'work',
             'identity': {'namespace': NS_A, 'id': HARDEN}}
    value.update(override)
    return value


def test_one_admission_boundary_admits_exact_identity_and_version_through_every_facet(workspace):
    """resolve, inspect and binding targets share admit_reference: exactly the supported owner, kind, identity keys
    and requested version, or the same typed refusal; nothing is re-canonicalised into another or current object."""
    ledger = w._ledger(workspace)
    current = w._task_revision(w._tasks(NS_A, workspace)[HARDEN])
    refusals = {
        'wrong-owner': (_work_ref(owner='domain.manuscript'), 'WRONG_OWNER'),
        'extra-identity-key': (_work_ref(identity={'namespace': NS_A, 'id': HARDEN, 'section': 's1'}), 'MALFORMED_REFERENCE'),
        'missing-identity-key': (_work_ref(identity={'id': HARDEN}), 'MALFORMED_REFERENCE'),
        'unsupported-kind': (identity.reference('domain.manuscript', 'document', {'id': 'living-guide'}), 'UNSUPPORTED_TARGET'),
        'unknown-subsystem': (sub('adapter.nowhere'), 'UNKNOWN_TARGET'),
        'wrong-owner-subsystem': (identity.reference('domain.work', 'subsystem', {'id': 'adapter.http'}), 'WRONG_OWNER'),
        'unknown-capability': (identity.reference('domain.work', 'capability', {'id': 'work.nowhere'}), 'UNKNOWN_TARGET'),
        'wrong-owner-capability': (identity.reference('domain.pipeline', 'capability', {'id': 'work.owner-discovery'}), 'WRONG_OWNER'),
        'stale-version': (_work_ref(version={'work_revision': 'sha256:' + '0' * 64}), 'STALE_VERSION'),
        'other-version-key': (_work_ref(version={'scope_revision': current}), 'UNSUPPORTED_VERSION'),
        'version-on-subsystem': ({**sub('adapter.http'), 'version': {'work_revision': current}}, 'UNSUPPORTED_VERSION')}
    lines = ledger.read_bytes()
    guard = lambda: {'namespace': NS_A, 'id': GUIDE, 'expected_work_revision': w._task_revision(w._tasks(NS_A, workspace)[GUIDE]),
                     'expected_binding_revision': od.current_binding(workspace, NS_A, GUIDE)['binding_revision']}
    for name, (value, code) in refusals.items():
        resolved = sdk.resolve(value, root=workspace)
        assert (resolved['status'], resolved['reference']) == (code, None), name
        with pytest.raises(od.DiscoveryRefusal) as inspected:
            sdk.inspect(value, root=workspace)
        assert inspected.value.details['code'] == code, name
        with pytest.raises(od.DiscoveryRefusal) as bound:
            sdk.bind({**guard(), 'relations': [{'relation': 'explains', 'target': value}]}, root=workspace)
        assert bound.value.details['code'] == code, name
    assert ledger.read_bytes() == lines
    stale = sdk.resolve(refusals['stale-version'][0], root=workspace)
    assert stale['current'] == {'work_revision': current} and stale['next_reads'][0]['request']['reference']['version'] == {'work_revision': current}
    # the exact current version, a legacy handle (unversioned) and an exact subsystem resolve as themselves
    exact = sdk.resolve(_work_ref(version={'work_revision': current}), root=workspace)
    assert exact['status'] == 'RESOLVED' and exact['version']['status'] == 'CURRENT' and exact['reference']['version'] == {'work_revision': current}
    assert sdk.inspect(_work_ref(version={'work_revision': current}), root=workspace)['version']['status'] == 'CURRENT'
    assert sdk.resolve(NS_A + '::' + HARDEN, root=workspace)['version']['status'] == 'UNVERSIONED'
    assert sdk.resolve(sub('adapter.http'), root=workspace)['next']['request'] == {'facet': 'discover', 'subsystem': 'adapter.http'}
    # private Work refuses exactly like absent Work for a project-confined caller
    private = native(workspace, NS_A, {'facet': 'resolve', 'reference': od.work_reference(NS_C, PRIVATE)})
    absent = native(workspace, NS_A, {'facet': 'resolve', 'reference': od.work_reference(NS_A, 'WORK-absent')})
    assert strip_scope(private) == strip_scope(absent) and private['status'] == 'NOT_IN_SCOPE'
    # after an owner edit, the once-current revision is stale: it is refused, never served as the current Work
    w.task(NS_A, {'id': HARDEN, 'title': 'Harden the shared interaction design', 'expected_work_revision': current}, workspace)
    with pytest.raises(od.DiscoveryRefusal) as moved:
        sdk.inspect(_work_ref(version={'work_revision': current}), root=workspace)
    assert moved.value.details['code'] == 'STALE_VERSION' and moved.value.details['requested'] == {'work_revision': current}


def test_admitted_input_and_returned_nested_values_do_not_alias_owner_rows(workspace):
    ledger = w._ledger(workspace)
    target = sub('core.identity')
    relations = [{'relation': 'explains', 'target': target}]
    payload = {'namespace': NS_A, 'id': GUIDE, 'expected_work_revision': w._task_revision(w._tasks(NS_A, workspace)[GUIDE]),
               'expected_binding_revision': od.current_binding(workspace, NS_A, GUIDE)['binding_revision'], 'relations': relations}
    result = sdk.bind(payload, root=workspace)
    facts = lambda: json.dumps(owner_intent([od.current_binding(workspace, NS_A, GUIDE), sdk.discover('core.identity', root=workspace),
                                sdk.inspect(od.work_reference(NS_A, GUIDE), root=workspace),
                                sdk.inspect(od.work_reference(NS_A, JOINS), root=workspace)]), sort_keys=True)
    before, lines = facts(), ledger.read_bytes()
    # the caller mutates what it passed in, and every nested value it got back
    target['identity']['id'] = 'adapter.http'
    relations.append({'relation': 'targets', 'target': sub('domain.work')})
    result['binding']['relations'][0]['target']['identity']['id'] = 'mutated'
    result['binding']['binding_revision'] = 'sha256:mutated'
    od.current_binding(workspace, NS_A, GUIDE)['relations'][0]['target']['identity']['id'] = 'mutated'
    for view in (sdk.inspect(od.work_reference(NS_A, GUIDE), root=workspace), sdk.inspect(od.work_reference(NS_A, JOINS), root=workspace)):
        for item in view['up'] + view['lateral']:
            if item.get('reference'):
                item['reference']['identity']['id'] = 'mutated'
    sdk.discover('core.identity', root=workspace)['items'][0]['reference']['identity']['namespace'] = 'mutated'
    assert facts() == before and ledger.read_bytes() == lines
    assert od.current_binding(workspace, NS_A, GUIDE)['relations'] == [{'relation': 'explains', 'target': sub('core.identity')}]


def test_selected_evidence_reads_through_its_owner_with_pins_gaps_and_continuation(workspace):
    """inspect carries the Work owner's evidence reads whole; the available one is read by its own owner (HTTP and
    native) with its pin, a changed or missing pinned file is refused by that owner, the unavailable one keeps its
    capability gap, and more than one page continues through the Work detail read."""
    from laplace.writing import operations
    programme = sdk.inspect(od.work_reference(NS_B, PROGRAMME), root=workspace)
    canonical = w.read(NS_B, {'view': 'detail', 'id': PROGRAMME}, workspace)['task']['evidence_reads']
    assert programme['evidence']['items'] == json.loads(json.dumps(canonical)) and programme['evidence']['truncated'] is False
    inside, outside = programme['evidence']['items']
    pin = inside['consumed_revision']   # the completion receipt's own spelling (bare hex), carried verbatim
    assert inside['available'] is True and len(pin) == 64 and 'expected_sha256=' + pin in inside['http']['url'], inside
    assert inside['operation'] == 'read_artifact' and inside['payload'] == {'path': 'evidence/programme.md', 'scope': 'project'}
    code, read = http(workspace, inside['http']['url'])
    assert code == 200 and read['content'] == 'R1-R5 physical programme: done\n'
    assert operations._execute(workspace, NS_B, 'work', inside['operation'], inside['payload'])['content'] == read['content']
    # outside the project's artifact home the repository material owner reads it: its own native payload and human read
    assert outside['available'] is True and outside['operation'] == 'material_references' and outside['human_read']['kind'] == 'material-source'
    assert outside['payload']['target'] == {'owner': 'repository', 'repository': 'laplace', 'path': OUTSIDE_EVIDENCE}
    material = operations._execute(workspace, NS_B, 'work', outside['operation'], outside['payload'])
    assert 'outside any project artifact home' in json.dumps(material)
    # once that file is gone the owner says the evidence is unavailable, with its gap and a read-only local coordinate
    (workspace / OUTSIDE_EVIDENCE).unlink()
    gone = sdk.inspect(od.work_reference(NS_B, PROGRAMME), root=workspace)['evidence']['items'][1]
    assert gone['available'] is False and gone['capability_gap'] and gone['local_read'] == {'path': OUTSIDE_EVIDENCE, 'read_only': True}, gone
    (workspace / PROGRAMME_EVIDENCE).write_text('Changed after completion\n')
    code, refused = http(workspace, inside['http']['url'])
    assert code == 409 and refused.get('error')
    assert sdk.inspect(od.work_reference(NS_B, PROGRAMME), root=workspace)['standing']['current_acceptance']['status'] != 'CURRENT'
    (workspace / PROGRAMME_EVIDENCE).unlink()
    code, missing = http(workspace, inside['http']['url'])
    assert code >= 400 and missing.get('error')
    hardening = sdk.inspect(od.work_reference(NS_A, HARDEN), root=workspace)
    page = hardening['evidence']
    assert (page['total'], len(page['items']), page['truncated']) == (EVIDENCE_TOTAL, od.EVIDENCE_PAGE, True)
    detail = w.read(NS_A, {'view': 'detail', 'id': HARDEN}, workspace)
    assert page['continuation'] == detail['task']['read_handle']
    code, full = http(workspace, page['continuation']['http']['url'])
    assert code == 200 and len(full['task']['evidence_reads']) == EVIDENCE_TOTAL and full['task']['evidence_reads'][:od.EVIDENCE_PAGE] == page['items']


# --------------------------------------------------------------------------------------------- correction: P0-R1a
def _versioned_bind(workspace, revision):
    return {'namespace': NS_A, 'id': GUIDE, 'expected_work_revision': w._task_revision(w._tasks(NS_A, workspace)[GUIDE]),
            'expected_binding_revision': od.current_binding(workspace, NS_A, GUIDE)['binding_revision'],
            'relations': [{'relation': 'consumes', 'target': _work_ref(version={'work_revision': revision})}]}


def test_a_target_version_moved_before_publication_refuses_inside_the_writer_lock(workspace, monkeypatch):
    """A binds to B at B's current revision b0. A real owner edit moves B to b1 after the binding was prepared and
    before its locked publication: the locked admission re-admits B's requested version, refuses STALE_VERSION and
    appends no binding; B's edit, B's history and A's current binding stay exactly as the owners left them."""
    b0 = w._task_revision(w._tasks(NS_A, workspace)[HARDEN])
    payload = _versioned_bind(workspace, b0)
    binding_before = od.current_binding(workspace, NS_A, GUIDE)
    real_append, moved = w._append, {}
    def interleave(root, row, *, admit=None):   # scheduling only: the real writer, admission and effects run
        if row.get('record') == od.BINDING_RECORD and not moved:
            moved['edit'] = w.task(NS_A, {'id': HARDEN, 'title': 'Harden the shared interaction design (edited)',
                                          'expected_work_revision': b0}, root)
        return real_append(root, row, admit=admit)
    monkeypatch.setattr(w, '_append', interleave)
    with pytest.raises(od.DiscoveryRefusal) as refused:
        sdk.bind(payload, root=workspace)
    monkeypatch.setattr(w, '_append', real_append)
    assert refused.value.details['code'] == 'STALE_VERSION' and refused.value.details['requested'] == {'work_revision': b0}
    b1 = w._task_revision(w._tasks(NS_A, workspace)[HARDEN])
    assert b1 != b0 and refused.value.details['current'] == {'work_revision': b1} and moved['edit']['work_revision'] == b1
    rows = w._rows(workspace)
    assert [row['record'] for row in rows].count(od.BINDING_RECORD) == len(ADOPTION())   # no binding was published
    assert od.current_binding(workspace, NS_A, GUIDE) == binding_before
    history = w.read(NS_A, {'view': 'history', 'id': HARDEN}, workspace)
    assert 'Harden the shared interaction design (edited)' in json.dumps(history)


def test_a_current_target_version_publishes_the_logical_target_and_reuse_is_readmitted(workspace):
    b0 = w._task_revision(w._tasks(NS_A, workspace)[HARDEN])
    target_before = w.read(NS_A, {'view': 'detail', 'id': HARDEN}, workspace)
    ledger = w._ledger(workspace)
    payload = _versioned_bind(workspace, b0)
    published = sdk.bind(payload, root=workspace)
    assert published['replayed'] is False
    logical = {key: value for key, value in od.work_reference(NS_A, HARDEN).items() if key not in ('version', 'legacy')}
    assert published['binding']['relations'] == [{'relation': 'consumes', 'target': logical}]   # stored without the version
    after = w.read(NS_A, {'view': 'detail', 'id': HARDEN}, workspace)
    assert after['read_cut'] == target_before['read_cut'] and after['task']['work_revision'] == b0   # the target is untouched
    lines = ledger.read_bytes()
    replay = sdk.bind(payload, root=workspace)      # the same request, B still at b0: reused inside the lock
    assert replay['replayed'] is True and replay['binding'] == published['binding'] and ledger.read_bytes() == lines
    w.task(NS_A, {'id': HARDEN, 'title': 'Harden the shared interaction design (edited)', 'expected_work_revision': b0}, workspace)
    lines = ledger.read_bytes()
    with pytest.raises(od.DiscoveryRefusal) as stale_reuse:   # reuse is acceptance too: B's moved revision refuses it
        sdk.bind(payload, root=workspace)
    assert stale_reuse.value.details['code'] == 'STALE_VERSION' and ledger.read_bytes() == lines
