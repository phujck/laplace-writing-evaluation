"""Bounded declared Source inputs, not a semantic index or a kernel identity registry.

The existing system description owns subsystem/module/capability relations. Existing
Source-contract providers own operation facts; repository/Material owners own source
reads. This pure projection never ingests, publishes, accepts or grants an effect.
"""
from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
import sys

from laplace import system
from laplace.core import identity
from laplace.projects import project_data, writing_sources
from laplace.work import source_contracts

SCHEMA = 'laplace.source-owner-inventory/1'
MAX_FILES, MAX_BYTES, MAX_FILE = 192, 8 * 1024 * 1024, 1024 * 1024
MAX_PAGE, DEFAULT_PAGE, MAX_RESPONSE = 20, 8, source_contracts.DEFAULT_BUDGET - 1024
# The declared input roles _inputs assigns; a role selection pages within the same cut, it never changes it.
INPUT_ROLES = ('contract-source', 'declared-input', 'declared-module', 'evaluator-source', 'explanation-source')
# One declared input body page through the owned workspace HTTP door, in Unicode characters of raw text.
INPUT_PAGE, MAX_INPUT_PAGE = 8000, 16000


def contract() -> dict:
    """The shared adapter derives this exact read shape; no parallel request grammar."""
    return {'type': 'object', 'required': ['facet', 'reference'], 'additionalProperties': False,
        'properties': {'facet': {'const': 'source-inventory'},
            'reference': {'type': 'object', 'required': ['schema_version', 'owner', 'kind', 'identity'],
                'additionalProperties': False, 'properties': {
                    'schema_version': {'const': 'laplace.reference/1'}, 'owner': {'const': 'core.identity'},
                    'kind': {'const': 'subsystem'}, 'identity': {'type': 'object', 'required': ['id'],
                        'additionalProperties': False, 'properties': {'id': {'type': 'string', 'minLength': 1, 'maxLength': 160}}}}},
            'offset': {'type': 'integer', 'minimum': 0, 'maximum': MAX_FILES},
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': MAX_PAGE},
            'as_of': {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'},
            'project_lens': {'type': 'string', 'minLength': 1, 'maxLength': 160},
            'role': {'enum': list(INPUT_ROLES)},
            'projection': {'const': 'inputs'}}}


def _handle(payload):
    from urllib.parse import urlencode
    request = identity.detached(payload) if hasattr(identity, 'detached') else dict(payload)
    query = {k: __import__('json').dumps(v, separators=(',', ':')) if isinstance(v, dict) else v for k, v in request.items()}
    return {'request': request, 'http': {'method': 'GET', 'url': '/work/discovery?' + urlencode(query)},
            'native': {'operation': 'project', 'payload': {'view': 'discovery', 'request': request}}}


def _kernel():
    return {'state': 'UNRESOLVED', 'reason_code': 'NO_EXPLICIT_KERNEL_COUNTERPART',
            'lookup_performed': False,
            'qualification': 'A declared source owner/input is not a memory-node identity. No mapping is declared here; this is not an absence census or fuzzy lookup.'}


def _eligible(rel):
    """Only bounded code/config and explicit public declaration families; no knowledge-tree expansion."""
    p = Path(rel)
    if project_data._excluded(p) or any(part.startswith('.') for part in p.parts):return False
    if rel.startswith(('src/laplace/pipeline/canon/', 'soul/', 'contract/', 'corpus_friction/', 'writing_projects/', 'projects/')):return False
    if rel == 'profiles/writing/sealed-reader-qualification.json':return False
    if rel.startswith('src/'):
        return p.suffix in {'.py', '.mjs', '.css', '.html'} or rel == 'src/laplace/system/description.json'
    if rel.startswith(('scripts/', 'tools/', 'tests/')):return p.suffix in {'.py', '.mjs', '.sh', '.csv', '.toml'}
    if rel.startswith('deploy/'):return p.suffix in {'.py', '.sh', '.yaml', '.yml', '.toml', '.dockerignore'} or p.name.startswith('Dockerfile')
    if rel.startswith('docs/'):return p.suffix == '.md'
    if rel.startswith('profiles/workflows/'):return p.name.endswith('.schema.json')
    return rel in system.OWNED_FILES or rel == 'atlas/pyproject.toml'


def _enumerate(root, base, pattern, *, modules=False):
    """Walk only a declared code/deploy prefix; broad docs/profiles/semantic families are not walked."""
    path = project_data._safe(root, base)
    if not path.exists():return []
    if path.is_file():return [base] if _eligible(base) else []
    if not (base in {'scripts', 'tools', 'deploy'} or base.startswith(('src/', 'scripts/', 'tools/', 'deploy/'))) or base.startswith('src/laplace/pipeline/canon'):
        return None
    found = []; directories = 0
    for directory, dirs, files in os.walk(path, followlinks=False):
        directories += 1
        if directories > MAX_FILES:raise ValueError('SOURCE_INVENTORY_BUDGET: declared directory bound exceeded.')
        for name in list(dirs):
            rel = (Path(directory) / name).relative_to(root)
            if project_data._excluded(rel) or name.startswith('.') or str(rel).startswith('src/laplace/pipeline/canon'):dirs.remove(name)
            else:project_data._safe(root, rel.as_posix())
        for name in files:
            rel = (Path(directory) / name).relative_to(root).as_posix()
            if not _eligible(rel):continue
            if modules and not rel.endswith('.py'):continue
            key = system.module_name(rel) if modules else rel
            if key and fnmatch.fnmatchcase(key, pattern):
                project_data._safe(root, rel);found.append(rel)
            if len(found) > MAX_FILES:raise ValueError('SOURCE_INVENTORY_BUDGET: declared source-file bound exceeded.')
    return found


def _inputs(root, description, owner):
    selected = {}; unavailable = []
    def add(path, role):selected.setdefault(path, set()).add(role)
    for pattern in owner['modules']:
        if not set(pattern) & set('*?['):
            stem = 'src/' + pattern.replace('.', '/')
            candidates = [stem + '.py', stem + '/__init__.py']
            if not any((root / rel).is_file() for rel in candidates):
                unavailable.append({'declaration': pattern, 'state': 'UNAVAILABLE', 'reason': 'Exact declared module is absent; no canonical/installed fallback.'})
        else:
            prefix = pattern.split('*', 1)[0].split('?', 1)[0].split('[', 1)[0].rstrip('.')
            candidates = _enumerate(root, 'src/' + prefix.replace('.', '/'), pattern, modules=True) or []
        for rel in candidates:
            if (root / rel).is_file() and _eligible(rel) and system.owner(description, rel)[0] == owner['id']:add(rel, 'declared-module')
    for pattern in owner['files']:
        if set(pattern) & set('*?['):
            prefix = pattern.split('*', 1)[0].split('?', 1)[0].split('[', 1)[0].rstrip('/')
            candidates = _enumerate(root, prefix, pattern)
            if candidates is None:
                unavailable.append({'declaration': pattern, 'state': 'NOT_EXPANDED', 'reason': 'Only declared code/deploy prefixes are expanded; knowledge, broad docs/profile and private inputs require their own admission.'});continue
        else:
            candidates = [pattern]
            if _eligible(pattern) and not project_data._safe(root, pattern).is_file():
                unavailable.append({'declaration': pattern, 'state': 'UNAVAILABLE', 'reason': 'Exact declared input is absent; no canonical/installed fallback.'})
        for rel in candidates:
            if _eligible(rel) and (root / rel).is_file() and system.owner(description, rel)[0] == owner['id']:add(rel, 'declared-input')
    for field, role in [('contracts', 'contract-source'), ('explanation', 'explanation-source'), ('evaluators', 'evaluator-source')]:
        for location in owner[field]:
            rel = location.split('#', 1)[0]
            if set(rel) & set('*?[') or not _eligible(rel):
                unavailable.append({'declaration': location, 'state': 'NOT_EXPANDED', 'reason': 'Not an admitted exact code/public declaration input.'});continue
            path = project_data._safe(root, rel)
            if path.is_file():add(rel, role)
            else:unavailable.append({'declaration': location, 'state': 'UNAVAILABLE', 'reason': 'Exact declared input is absent; no canonical/installed fallback.'})
    if len(selected) > MAX_FILES:raise ValueError('SOURCE_INVENTORY_BUDGET: selected owner exceeds file bound.')
    return selected, unavailable


# The three standing qualifications of every current declaration row. Each uncompacted row carries them in full; a
# compacted response states them once in coverage.metadata.row_qualifications instead of repeating them per row.
_CURRENT_READ_QUALIFICATION = 'Exact typed consumer rows are in existing selected segment reads. These current reads are not retained-version custody: compare their returned version/basis with this observation.'
_LOADED_CODE_QUALIFICATION = 'The provider result is observed in this runtime; the raw pin observes current disk source. Equal disk bytes do not prove the loaded Python code or all dependencies. Same-path edits after import are not detected as loaded-code changes.'
_DISK_PIN_QUALIFICATION = 'Observed runtime declaration and separately observed source pin. Disk-source equality is a prerequisite for this projection, not verified attribution to loaded code. Not retained historical custody, reviewed acceptance, executable check result or all-dependency equivalence.'


def _runtime_source_linkage():
    return {'state': 'UNVERIFIED_LOADED_CODE', 'loaded_code_asserted': False, 'qualification': _LOADED_CODE_QUALIFICATION}


def _kernel_publications_read(owner,operation,scope):
    # One explicit historical publication choice, separate from observed current inventory version.
    # Keep request+HTTP for exact consumer verification without duplicating native wrappers per row.
    from laplace.work.source_kernel import handle
    value=handle({'facet':'source-kernel','reference':source_contracts.reference(owner,operation),
                  **({'namespace':scope.namespace} if getattr(scope,'kind',None)=='project' else {})})
    return {key:value[key] for key in ('request','http')}


def _contracts(root, description, owner_id, *, scope=None):
    rows = []
    # Only the existing provider registry; no source-contract discovery scan/import sweep.
    for provider in source_contracts.providers():
        module = sys.modules[provider.__module__];rel = 'src/' + provider.__module__.replace('.', '/') + '.py'
        if system.owner(description, rel)[0] != owner_id:continue
        executing = Path(module.__file__).resolve()
        if not (root / rel).is_file():continue
        target = project_data._safe(root, rel)
        observed = project_data._file_record(root, target)
        actual = project_data._file_record(executing.parent, executing)
        if observed['sha256'] != actual['sha256']:
            rows.append({'state': 'UNAVAILABLE', 'declaring_module': provider.__module__, 'reason': 'Executing declaration source and selected source edition differ; runtime facts not substituted.'});continue
        declaration = provider()
        if declaration['owner'] != owner_id:continue
        version = source_contracts.version(declaration)
        reference = source_contracts.reference(owner_id, declaration['operation'])
        coarse = source_contracts.inspect(declaration)
        coarse_read = _handle({'facet': 'inspect', 'reference': reference})
        selective = {'request': coarse_read['request'], 'field': 'select', 'http': coarse_read['http'], 'query_field': 'select',
            'values': {row['id']: row['next']['select'] for row in coarse['segments']}}
        rows.append({'state': 'CURRENT_DECLARATION_ONLY', 'reference': reference,
            'observed_version': version, 'segment_bases': source_contracts.bases(declaration),
            'source_kernel_read': _kernel_publications_read(owner_id,declaration['operation'],scope),
            'relation_counts': coarse['relations'], 'segment_reads': selective,
            'coverage': {'relations': 'COUNTS_ONLY', 'known_relations': len(declaration['relations']), 'inline_relation_rows': 0,
                'qualification': _CURRENT_READ_QUALIFICATION},
            'declaring_source': observed,
            'runtime_source_linkage': _runtime_source_linkage(),
            'read': coarse_read,
            'qualification': _DISK_PIN_QUALIFICATION,
            'kernel': {'state': 'UNRESOLVED', 'reason_code': 'NO_EXPLICIT_KERNEL_COUNTERPART'}})
    return rows


_COMPACT_CONTRACT_FIELDS = ('state', 'reference', 'observed_version', 'declaring_module', 'reason', 'declaring_source',
                            'source_kernel_read', 'relation_counts', 'read', 'kernel')
# Every per-row field a compacted contract or capability omits, and where its meaning is read.
_OMITTED_CONTRACT_FIELDS = {
    'segment_bases': "The row's read is a coarse source-contract inspection listing every segment id with its basis.",
    'segment_reads': "The same coarse inspection issues each segment's select handle; select one segment or step for its facts.",
    'coverage': 'Relation counts stay in relation_counts; typed consumer rows are in selected segment reads; its qualification is row_qualifications.current_read.',
    'runtime_source_linkage': 'The same for every marked row: row_qualifications.runtime_source_linkage.',
    'qualification': 'The same for every marked row: row_qualifications.disk_pin.'}
_OMITTED_CAPABILITY_FIELDS = {'summary': "Omitted here only; the capability's read is its existing inspect read."}


def _compact_metadata(result, *, response_bytes):
    """Bound an assembled response over MAX_RESPONSE before any source row is given up. Each contract keeps its identity,
    observed version, declaring-source pin, relation counts and its coarse inspect and kernel reads; each capability keeps
    identity, operation basis and read; unavailable rows are grouped by (state, reason) with every declaration. The three
    standing row qualifications are stated once and each omitted field names where its meaning is read. A row whose
    qualifications differ from the shared ones keeps its own. The basis (computed over the full metadata) is unchanged."""
    fixed_bytes = len(json.dumps({**result, 'items': [], 'relations': []}, ensure_ascii=False).encode())
    contracts = result['contracts'];capabilities = result['capabilities'];unavailable = result['coverage'].get('unavailable') or []
    compact = []
    for row in contracts:
        kept = {key: row[key] for key in _COMPACT_CONTRACT_FIELDS if key in row}
        if row.get('segment_bases'):kept['segments'] = len(row['segment_bases'])
        if row.get('state') == 'CURRENT_DECLARATION_ONLY':
            shared = (row.get('runtime_source_linkage') == _runtime_source_linkage() and row.get('qualification') == _DISK_PIN_QUALIFICATION
                      and (row.get('coverage') or {}).get('qualification') == _CURRENT_READ_QUALIFICATION)
            if shared:kept['qualifications'] = 'coverage.metadata.row_qualifications'
            else:kept.update({key: row[key] for key in ('runtime_source_linkage', 'coverage', 'qualification') if key in row})
        compact.append(kept)
    result['contracts'] = compact
    result['capabilities'] = [{key: row[key] for key in ('reference', 'operation_basis', 'read') if key in row} for row in capabilities]
    groups = {}
    for row in unavailable:groups.setdefault((row.get('state'), row.get('reason')), []).append(row.get('declaration'))
    result['coverage']['unavailable'] = [{'state': state, 'reason': reason, 'declarations': names} for (state, reason), names in groups.items()]
    result['coverage']['metadata'] = {'state': 'COMPACT', 'contracts': len(contracts), 'capabilities': len(capabilities),
        'unavailable': len(unavailable), 'unavailable_groups': len(groups),
        'trigger': {'response_bytes': response_bytes, 'fixed_metadata_bytes': fixed_bytes, 'budget': MAX_RESPONSE,
            'reason': 'Fixed declaration metadata alone exceeds the bounded read.' if fixed_bytes > MAX_RESPONSE else
                      'The assembled response exceeds the bounded read; metadata is compacted before any source row is given up.'},
        'row_qualifications': {'runtime_source_linkage': _runtime_source_linkage(), 'current_read': _CURRENT_READ_QUALIFICATION,
            'disk_pin': _DISK_PIN_QUALIFICATION, 'applies_to': 'Every contract row marked qualifications. Its declaring_source pin observes disk bytes only and is not loaded-code attribution.'},
        'omitted_fields': {'contracts': dict(_OMITTED_CONTRACT_FIELDS), 'capabilities': dict(_OMITTED_CAPABILITY_FIELDS)},
        'contract_reads': "A contract row's read is a coarse source-contract inspection (segment and step ids, bases, select handles, relation counts), not the full declaration; full facts come from selecting one segment or step."}


def read(root, scope, payload):
    from jsonschema import Draft202012Validator
    from laplace.core.identity import canonical_digest
    import json
    issue = next(Draft202012Validator(contract()).iter_errors(payload), None)
    if issue:raise ValueError('Malformed source inventory request: ' + issue.message)
    inputs_only = payload.get('projection') == 'inputs'
    root = Path(root).resolve();reference = payload['reference'];owner_id = reference['identity']['id']
    lens = payload.get('project_lens') or getattr(scope, 'namespace', None)
    if lens:
        from laplace.pipeline import registry
        if not scope.admits(lens) or lens not in registry.all_projects(repo_root=root):raise ValueError('Source inventory project lens is unavailable in this scope.')
    descriptor = project_data._safe(root, 'src/laplace/system/description.json')
    if not descriptor.is_file():
        return {'schema_version': SCHEMA, 'state': 'UNAVAILABLE', 'reference': reference,
            'reason_code': 'SOURCE_DESCRIPTION_UNAVAILABLE', 'kernel': _kernel(), 'basis': None,
            'items': [], 'contracts': [], 'coverage': {'source': 'Explicit owned root only; no installed/canonical fallback.',
                **({'contract_relations': 'NOT_REQUESTED', 'capabilities': 'NOT_REQUESTED'} if inputs_only else {})},
            **({'projection': 'inputs', 'capabilities': []} if inputs_only else {})}
    description = system.load(descriptor);owners = system.subsystems(description)
    if owner_id not in owners:raise ValueError('Unknown exact declared source owner.')
    owner = owners[owner_id];selected, unavailable = _inputs(root, description, owner)
    records = [];total = 0
    for rel, roles in sorted(selected.items()):
        path = project_data._safe(root, rel)
        if path.stat().st_size > MAX_FILE:raise ValueError('SOURCE_INVENTORY_BUDGET: input exceeds per-file bound.')
        row = project_data._file_record(root, path);total += row['bytes']
        if total > MAX_BYTES:raise ValueError('SOURCE_INVENTORY_BUDGET: selected owner exceeds byte bound.')
        records.append({**row, 'roles': sorted(roles), 'module': system.module_name(rel),
            'classification': 'evaluator-source-not-executed' if roles == {'evaluator-source'} else 'declaration-source' if 'contract-source' in roles else 'source-code' if rel.endswith('.py') else 'declared-input',
            'kernel': {'state': 'UNRESOLVED', 'reason_code': 'NO_EXPLICIT_KERNEL_COUNTERPART'}})
    routes = {}
    for row in records:
        try:routes[row['path']] = writing_sources.target_for_path(root, row['path'])
        except (ValueError, OSError):routes[row['path']] = None
    from laplace.work import owner_discovery
    kernel_scope=owner_discovery.project_scope(lens,scope.door) if lens else scope
    # Inputs descent does not build the unrequested rich declaration metadata.
    declarations = [] if inputs_only else _contracts(root, description, owner_id, scope=kernel_scope)
    description_pin = project_data._file_record(root, descriptor)
    basis = canonical_digest({'owner': owner, 'description': description_pin, 'inputs': records, 'contracts': declarations, 'unavailable': unavailable, 'source_read_routes': routes})
    if payload.get('as_of') and payload['as_of'] != basis:raise ValueError('CHANGED_INPUT: source inventory changed; explicitly reinspect current.')
    offset = payload.get('offset', 0);limit = payload.get('limit', DEFAULT_PAGE)
    # A role selection (for example the declared explanation) pages inside the same cut and basis.
    listed = [row for row in records if payload['role'] in row['roles']] if payload.get('role') else records
    if offset > len(listed):raise ValueError('Source inventory offset is outside selected coverage.')
    page = json.loads(json.dumps(listed[offset:offset + limit]))
    for row in page:
        try:
            target = routes[row['path']]
            if target is None:raise ValueError('No configured source route.')
            request = {'action': 'read', 'repository': target['repository'], 'path': target['path'], 'expected_sha256': row['sha256'], 'offset': 0, 'limit': 2000}
            row['read'] = {'operation': 'repository', 'payload': request,
                'python': {'module': 'laplace.projects.writing_sources', 'method': 'execute', 'arguments': 'root and this read.payload'}}
            if lens:
                from laplace.projects import library
                human = library.material_read_handle(lens, {'view': 'preview', 'target': target, 'expected_sha256': row['sha256'], 'offset': 0, 'limit': 2000})
                row['read']['http'] = human['http'];row['read']['human_read'] = human['human_read']
            elif getattr(scope, 'kind', None) == 'owned-workspace' and getattr(scope, 'door', None) == 'http':
                # The owned workspace HTTP door's own bounded body read; it re-proves this row at this cut before any byte.
                body = _handle({'facet': 'source-input', 'reference': reference, 'as_of': basis, 'path': row['path'],
                                'expected_sha256': row['sha256'], **({'projection': 'inputs'} if inputs_only else {})})
                row['read']['workspace_read'] = {'request': body['request'], 'http': body['http'],
                    'scope': 'Owned workspace HTTP door only; native and project callers use the repository read of this row.'}
        except (ValueError, OSError):
            row['read'] = None;row['read_unavailable'] = 'No unique configured repository read for this exact source; pin is retained, no alias/namespace invented.'
    # Detect source movement during the observation; never mix two byte editions.
    for row in records:
        if project_data._file_record(root, project_data._safe(root, row['path']))['sha256'] != row['sha256']:raise ValueError('CHANGED_INPUT: source moved during inventory observation.')
    for rel, target in routes.items():
        try:current_route = writing_sources.target_for_path(root, rel)
        except (ValueError, OSError):current_route = None
        if current_route != target:raise ValueError('CHANGED_INPUT: configured source reader changed during observation.')
    if project_data._file_record(root, descriptor)['sha256'] != description_pin['sha256']:raise ValueError('CHANGED_INPUT: source description moved during observation.')
    base = {k:v for k,v in payload.items() if k not in {'as_of','offset'}}
    result = {'schema_version': SCHEMA, 'state': 'PARTIAL' if unavailable else 'AVAILABLE', 'reference': reference,
        'basis': basis, 'description': description_pin, 'scope': scope.public(), 'items': page,
        'contracts': declarations, 'relations': [{'relation': 'contains', 'owner': reference, 'input': {'path': r['path'], 'sha256': r['sha256']}, 'roles': r['roles']} for r in page],
        'capabilities': [] if inputs_only else [{'reference': system.capability_reference(r), 'summary': r['summary'], 'operation_basis': canonical_digest(r.get('operation', {})),
            'read': {'request': {'facet': 'inspect', 'reference': system.capability_reference(r)}}} for r in description.get('capabilities', []) if r.get('owner') == owner_id],
        'kernel': _kernel(), 'execution_evidence': {'state': 'NOT_ASSERTED', 'qualification': 'Evaluator source and declared relations are not executed test/review evidence. Use existing Source-contract current-standing reads for canonical acceptance.'}, 'coverage': {'owner': owner_id, 'known': len(listed), **({'role': payload['role'], 'declared_inputs': len(records)} if payload.get('role') else {}), 'returned': len(page), 'source_bytes_observed': total,
            'unavailable': unavailable, 'atomic': False, 'contract_relations': 'Counts with existing issued segment reads; no inline schemas or relation bodies.', 'capabilities': 'Identity, purpose and operation basis with existing inspect read; operation body omitted.', 'qualification': 'Declared selected-owner code/inputs only. Source/evaluator declarations are not executed evidence, review acceptance or kernel ingestion.'},
        'pagination': {'offset': offset, 'cut': basis, 'next_read': _handle({**base, 'offset': offset + len(page), 'as_of': basis}) if offset + len(page) < len(listed) else None,
            'current_read': _handle({**base, 'offset': 0})}}
    if inputs_only:
        result['projection'] = 'inputs'
        result['coverage']['contract_relations'] = 'NOT_REQUESTED'
        result['coverage']['capabilities'] = 'NOT_REQUESTED'
    # A requested count is an upper bound, just as in the existing bounded Work reads.
    # Keep a complete qualified continuation instead of emitting an over-budget native reply.
    result['coverage']['response_budget_bytes'] = MAX_RESPONSE
    result['coverage']['requested_limit'] = limit
    # An over-budget response compacts its metadata before any source row is given up, so a default read still returns rows.
    size = len(json.dumps(result, ensure_ascii=False).encode())
    if size > MAX_RESPONSE:_compact_metadata(result, response_bytes=size)
    while len(json.dumps(result, ensure_ascii=False).encode()) > MAX_RESPONSE and page:
        page.pop();result['relations'] = result['relations'][:len(page)]
        result['coverage']['returned'] = len(page)
        result['pagination']['next_read'] = _handle({**base, 'offset': offset + len(page), 'as_of': basis})
    if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_RESPONSE or not page and offset < len(listed):
        raise ValueError('SOURCE_INVENTORY_BUDGET: fixed declaration metadata or one source row exceeds the bounded read.')
    return json.loads(json.dumps(result))


def input_contract() -> dict:
    """One declared inventory row's bounded body: the closed selector of the owned workspace HTTP door."""
    inventory = contract()['properties']
    return {'type': 'object', 'required': ['facet', 'reference', 'as_of', 'path', 'expected_sha256'], 'additionalProperties': False,
        'properties': {'facet': {'const': 'source-input'}, 'reference': inventory['reference'], 'as_of': inventory['as_of'],
            'path': {'type': 'string', 'minLength': 1, 'maxLength': 400},
            'expected_sha256': {'type': 'string', 'pattern': '^(sha256:)?[0-9a-f]{64}$'},
            'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': MAX_INPUT_PAGE},
            'projection': {'const': 'inputs'}}}


def _web(handle):
    # The body read is an HTTP-door read only: no native companion is issued for it.
    return {'request': handle['request'], 'http': handle['http']}


def read_input(root, scope, payload):
    """Bounded exact bytes of ONE declared input row, read through the owned workspace HTTP door.

    The inventory owner re-proves the selection before any byte: the same inventory cut (CHANGED_INPUT otherwise), the
    row's membership in the selected owner and its whole-file pin. The configured repository target is derived here from
    the row, never from the caller. Project, native and SDK scopes refuse before the body. No path, alias or project in the
    request grants access; the returned page carries no filesystem path.
    """
    from jsonschema import Draft202012Validator
    issue = next(Draft202012Validator(input_contract()).iter_errors(payload), None)
    if issue:raise ValueError('Malformed source input request: ' + issue.message)
    if getattr(scope, 'kind', None) != 'owned-workspace' or getattr(scope, 'door', None) != 'http':
        raise ValueError('SOURCE_INPUT_DOOR: a declared input body is read through the owned workspace HTTP door only; '
                         "native, SDK and project callers use the inventory row's repository read. Nothing was read.")
    root = Path(root).resolve();reference = payload['reference']
    inventory = {'facet': 'source-inventory', 'reference': reference, 'as_of': payload['as_of'], 'offset': 0, 'limit': 1,
                 **({'projection': 'inputs'} if payload.get('projection') == 'inputs' else {})}
    read(root, scope, inventory)    # the one owner of the cut: a moved inventory refuses CHANGED_INPUT before any body
    description = system.load(project_data._safe(root, 'src/laplace/system/description.json'))
    owner = system.subsystems(description)[reference['identity']['id']]
    selected, _ = _inputs(root, description, owner)
    rel = payload['path']
    if rel not in selected:
        raise ValueError('SOURCE_INPUT_UNDECLARED: this path is not a declared input of the selected owner. Nothing was read.')
    record = project_data._file_record(root, project_data._safe(root, rel))
    if str(record['sha256']).removeprefix('sha256:') != payload['expected_sha256'].removeprefix('sha256:'):
        raise ValueError('CHANGED_INPUT: the selected input bytes changed since this inventory row; explicitly reinspect the current inventory.')
    target = writing_sources.target_for_path(root, rel)
    offset = payload.get('offset', 0);limit = payload.get('limit', INPUT_PAGE)
    base = {key: value for key, value in payload.items() if key not in {'offset', 'limit'}}
    restart = _web(_handle({key: value for key, value in inventory.items() if key not in {'as_of', 'offset', 'limit'}}))
    while True:
        body = writing_sources.execute(root, {'action': 'read', 'repository': target['repository'], 'path': target['path'],
                                              'expected_sha256': record['sha256'], 'offset': offset, 'limit': limit})
        following = body.get('next_offset')
        result = {'schema_version': 'laplace.source-input-read/1', 'facet': 'source-input', 'state': 'AVAILABLE',
            'reference': reference, 'cut': payload['as_of'], 'scope': scope.public(),
            'input': {'path': rel, 'sha256': record['sha256'], 'bytes': record['bytes'], 'roles': sorted(selected[rel])},
            'content': body.get('content') or '', 'offset': offset, 'limit': limit, 'units': body.get('units'),
            'total_lines': body.get('total_lines'), 'truncated': bool(body.get('truncated')), 'next_offset': following,
            'pagination': {'page_read': _web(_handle({**base, 'offset': offset, 'limit': limit})),
                'next_read': _web(_handle({**base, 'offset': following, 'limit': limit})) if following is not None else None,
                'previous_read': _web(_handle({**base, 'offset': max(0, offset - limit), 'limit': limit})) if offset > 0 else None,
                'restart_read': restart},
            'qualification': ('The exact declared input bytes at this inventory cut, read for orientation. Reading them is not '
                              'execution, review, publication or a claim about loaded runtime code.')}
        size = len(json.dumps(result, ensure_ascii=False).encode())
        if size <= MAX_RESPONSE or limit <= 256:break
        limit = max(256, limit // 2)   # a smaller exact page of the same bytes, never a cap increase
    if size > MAX_RESPONSE:raise ValueError('SOURCE_INPUT_BUDGET: one bounded page of this input exceeds the response budget.')
    return result
