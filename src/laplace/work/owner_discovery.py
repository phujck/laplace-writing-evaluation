"""Owner-qualified discovery of Work, and the Work-owned bindings it reads (P0a, Root grant 2026-10-21).

Ownership
  A section of the project_work owner. Truth stays where it was: Work specifications, standings, phases and
  observations in ``corpus_friction/work_orders.jsonl`` and their folds (``project_work``), qualified activity
  (``project_work_activity``), detail projections and handles (``project_work_views``). This module adds one
  record kind to that same ledger, ``project-work-binding``, and the reads that follow it. The subsystem and
  capability declarations come from ``laplace.system`` (core); this domain reads them, never the reverse.

Bindings (``bind``)
  A binding row names, for one existing Work ``(namespace, id)``, typed relations to owner-qualified references
  (``laplace.core.identity.reference``): ``responsible-owner`` (a subsystem), ``targets``, ``coordinates``,
  ``consumes`` and ``explains`` (a subsystem, a declared capability or another existing Work). It is separately
  revisioned (a requested target Work version is compared under the writer lock, then the logical target is
  stored without it): ``binding_revision`` chains the prior revision, and the Work's specification, scope, standing,
  completion, evidence and phases are untouched (the row is not in ``project_work._WORK_RECORDS``, so no Work
  revision, read cut or review basis moves). Admission compares the supplied ``expected_work_revision`` (the
  specification guard every Work edit uses) and ``expected_binding_revision`` (null for the first binding) inside
  the ledger's writer lock, through ``project_work._append`` and its owner receipt. Replaying a request that is
  already the current binding returns it with ``replayed`` and appends nothing; a stale guard appends nothing.
  A binding transfers no authority: every effect on the Work still goes through its original admitted action.

Scope (who is asking)
  ``Scope`` is supplied by the trusted host, never by a payload: the local owned workspace (the SDK over its own
  root, the local HTTP door) or one project (a native session's namespace). Results contain only Work whose
  namespace the scope admits. Out-of-scope Work is not counted, titled or identified; an inspect or resolve of it
  is refused exactly like an unknown target. Reading metadata grants no body, source or execution access.

Reads (one request contract, ``contract()``; one result shape, ``RESULT_SCHEMA``)
  describe  system grade: the declared purpose and subsystem/capability references, the task's declared-word
            choices (``laplace.system.choices``; never a guessed owner), each subsystem's bound-Work count in scope
            and its next descent handle.
  discover  subsystem grade: the in-scope Work bound to one subsystem (directly or through a capability it owns),
            in the LIST projection with the matching relations, paged under a read cut, with an upward summary.
  inspect   Work grade: the canonical detail selected to purpose, standing, blockers, qualified activity (an
            expired observation is UNKNOWN, as its owner says), next actions, evidence handles, the binding, the
            parent, and upward and lateral references (outgoing relations, and incoming ones from in-scope bindings)
            with their next handles.
  resolve   a reference, a legacy ``namespace::id`` or a legacy ``project`` read handle to the canonical
            reference; a bare id names choices when several in-scope namespaces hold it.
  References are admitted by one boundary (``admit_reference``) for resolve, inspect and binding targets: exact
  supported owner, kind, identity keys and requested version (a Work revision is CURRENT or STALE_VERSION, never
  silently replaced by the current object). Admitted input and every public result are JSON copies, detached from
  the owner's cached rows.
  Doors: the SDK (``laplace.sdk``, owned workspace), ``GET /work/discovery`` (the local HTTP door, owned workspace)
  and the native Work read ``project {"view": "discovery", "request": {...}}`` (the session's project), all with
  this one request contract; every returned handle spells all three.
  Coverage is explicit on every result: unbound Work is not listed, so absence from a page never claims that no
  Work exists.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import uuid
from dataclasses import dataclass
from urllib.parse import urlencode

from laplace.core import identity
from laplace.work import project_work as work

BINDING_RECORD = 'project-work-binding'
BINDING_SCHEMA = 'laplace.work-binding/1'
RESULT_SCHEMA = 'laplace.owner-discovery/1'
RELATIONS = ('responsible-owner', 'targets', 'coordinates', 'consumes', 'explains')
TARGET_KINDS = ('subsystem', 'capability', 'work')
MAX_RELATIONS = 16
PAGE, MAX_PAGE = 10, 50
EVIDENCE_PAGE = 5
TEXT = 600
UNBOUND = ('Only Work bound to an owner through this owner is listed. Work without a binding is not listed, so its '
           'absence here is not a claim that no other Work exists.')


@dataclass(frozen=True)
class Scope:
    """The caller's actual read scope, constructed by the adapter from trusted host facts (never a payload)."""
    kind: str                                   # 'owned-workspace' | 'project'
    door: str                                   # 'sdk' | 'http' | 'native'
    namespace: str | None = None

    def admits(self, namespace) -> bool:
        return self.kind == 'owned-workspace' or namespace == self.namespace

    def public(self) -> dict:
        if self.kind == 'owned-workspace':
            return {'kind': self.kind, 'door': self.door,
                    'says': 'The local owned workspace: every namespace this root holds is readable here.'}
        return {'kind': self.kind, 'door': self.door, 'namespace': self.namespace,
                'says': 'Confined to this project. Work elsewhere is neither listed, counted nor named; its own '
                        'owner admits other readers separately.'}


def owned_workspace(door: str) -> Scope:
    return Scope('owned-workspace', door)


def project_scope(namespace: str, door: str) -> Scope:
    if not isinstance(namespace, str) or not namespace:
        raise ValueError('A project scope names its exact namespace.')
    return Scope('project', door, namespace)


# ------------------------------------------------------------------------------------------------ contracts
def contract() -> dict:
    """The one request contract of the SDK, native ``discover`` and ``GET /work/discovery``."""
    return {'type': 'object', 'properties': {
        'facet': {'enum': ['describe', 'resolve', 'discover', 'inspect', 'workspace', 'object', 'dependents', 'handover', 'input', 'object-request', 'manuscript-selection', 'neighbourhood', 'semantic-scope', 'timeline', 'source-inventory','source-input','source-kernel','historical-obligations']},
        'task': {'type': 'string', 'maxLength': 400},
        'subsystem': {'type': 'string', 'maxLength': 120},
        'reference': {'oneOf': [{'type': 'object'}, {'type': 'string', 'maxLength': 400}]},
        'offset': {'type': 'integer', 'minimum': 0},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 40000},
        'as_of': {'type': 'string', 'maxLength': 80},
        'project_lens': {'type': 'string', 'minLength': 1},
        # a source-inventory role selection and one declared source-input row (their facets own the closed schemas below)
        'role': {'type': 'string', 'maxLength': 40}, 'path': {'type': 'string', 'maxLength': 400},
        # The source-inventory facet owns the selector's closed schema below.
        'projection': {},
        'family': {'enum': ['all','work','concept','research-record','reference','artifact','workflow-definition']},
        'section': {'enum': ['purpose','standing','relationships','inputs_outputs','settings','actions','feedback','history','body']},
        'coordinate': __import__('laplace.work.object_geometry',fromlist=['COORDINATE']).COORDINATE,
        'relations': {'type':'array','uniqueItems':True,'minItems':1,'maxItems':7,'items':{'enum':list(__import__('laplace.work.object_geometry',fromlist=['RELATIONS']).RELATIONS)}},
        'lane': {'type':'string','minLength':1,'maxLength':120},
        'changed_basis': {'type': ['string','null']}, 'change_kind': {'enum': ['version','assumption']},
        'read': {'type':'object'}, 'object_request': {'type':'object'},
        # a source-contract inspect only (work.source_contracts.normalize): one constituent and the whole-envelope byte budget
        'semantic_handle':{'type':'string'},'fold_receipt_handle':{'type':'string'},'publication_handle':{'type':'string'},'content_handle':{'type':'string'},'node_id':{'type':'string'},'namespace':{'type':'string'},'view':{'type':'string'},'selection':{'type':'object'},'segments':{'type':'array'},'source':{'type':'string'},'state':{'type':'string'},'id':{'type':'string'},'expected_sha256':{'type':'string'},'content_offset':{'type':'integer'},
        'select': {'type': 'string', 'maxLength': 80}, 'budget': {'type': 'integer', 'minimum': 1}}, 'additionalProperties': False,
        'allOf':[{'if':{'anyOf':[{'properties':{'facet':{'const':'object'},'section':{'const':'body'}},'required':['facet','section']},
                                 {'properties':{'facet':{'const':'source-input'}},'required':['facet']}]},
                  'then':{},'else':{'properties':{'limit':{'maximum':MAX_PAGE}}}},
                 {'if':{'properties':{'facet':{'const':'source-input'}},'required':['facet']},
                  'then':__import__('laplace.work.source_inventory',fromlist=['input_contract']).input_contract()},
                 {'if':{'properties':{'facet':{'const':'source-inventory'}},'required':['facet']},
                  'then':__import__('laplace.work.source_inventory',fromlist=['contract']).contract()},
                 {'if':{'properties':{'facet':{'const':'source-kernel'}},'required':['facet']},'then':__import__('laplace.work.source_kernel',fromlist=['contract']).contract()},
                 {'if':{'properties':{'facet':{'const':'historical-obligations'}},'required':['facet']},'then':__import__('laplace.engine.historical_obligations',fromlist=['contract']).contract()}]}


def binding_contract() -> dict:
    """The admission schema of a binding (``POST /work/binding``, ``laplace.sdk.bind``)."""
    target = {'type': 'object'}   # its shape is the owner's typed answer (identity.reference_problems)
    return {'type': 'object', 'required': ['namespace', 'id', 'expected_work_revision', 'expected_binding_revision', 'relations'],
            'properties': {
                'namespace': {'type': 'string', 'minLength': 1}, 'id': {'type': 'string', 'minLength': 1},
                'expected_work_revision': {'type': 'string', 'minLength': 1},
                'expected_binding_revision': {'type': ['string', 'null']},
                'relations': {'type': 'array', 'minItems': 1, 'maxItems': MAX_RELATIONS, 'items': {
                    'type': 'object', 'required': ['relation', 'target'], 'additionalProperties': False,
                    'properties': {'relation': {'enum': list(RELATIONS)}, 'target': target}}},
                'by': {'type': 'string', 'maxLength': 120}}, 'additionalProperties': False}


def handle(payload: dict) -> dict:
    """The next read, spelled once for every door. ``request`` is the shared contract payload (``laplace.sdk.request``);
    the native door carries it inside the Work read (``project {"view": "discovery", "request": ...}``, scoped to the
    session's project) and the local HTTP door as ``GET /work/discovery``."""
    flat = {key: (json.dumps(value, sort_keys=True, separators=(',', ':')) if isinstance(value, (dict,list)) else value)
            for key, value in payload.items()}
    return {'request': dict(payload),
            'native': {'operation': 'project', 'payload': {'view': 'discovery', 'request': dict(payload)}},
            'http': {'method': 'GET', 'url': '/work/discovery?' + urlencode(flat)}}


def work_reference(namespace: str, ident: str, *, revision=None) -> dict:
    """The owner-qualified reference of an existing Work; its native identity is the exact (namespace, id) pair."""
    from laplace.work.project_work_views import handle as work_handle
    return identity.reference('domain.work', 'work', {'namespace': namespace, 'id': ident},
                              version={'work_revision': revision} if revision else None,
                              legacy={'qualified_id': namespace + '::' + ident,
                                      'read': work_handle(namespace, {'view': 'detail', 'id': ident})})


class DiscoveryRefusal(ValueError):
    """A typed local result: the code, what to read next, and nothing about objects outside the caller's scope."""
    def __init__(self, code: str, message: str, *, next_reads=(), choices=None, **facts):
        super().__init__(message)
        self.details = {'code': code, 'next_reads': list(next_reads), **({'choices': choices} if choices is not None else {}),
                        **_detached(facts)}


def _detached(value):
    """A JSON copy: admitted input and every public result share no object with the owner's cached rows."""
    return json.loads(json.dumps(value))


# ------------------------------------------------------------------------------------------------ reference admission
#: the supported kinds, their exact native identity keys and their responsible owner (None: the declaration names it)
_SUPPORTED = {'subsystem': ({'id'}, 'core.identity'), 'capability': ({'id'}, None), 'work': ({'namespace', 'id'}, 'domain.work')}


def admit_reference(root, scope: Scope, value, *, description=None, read_context=None) -> dict:
    """THE reference admission of this owner, used by resolve, inspect and binding targets.

    A reference is admitted only as exactly what it names: a supported kind, its exact identity keys, the owner
    that is responsible for it, an object that exists (and, for Work, is readable in ``scope``), and a requested
    version this owner can compare. Work is the one versioned kind here: ``version: {"work_revision": ...}`` is
    CURRENT when it equals the Work's specification revision and refused as STALE_VERSION otherwise (with the
    current reference to read instead); no history is reconstructed. A version on any other kind, or another
    version key, is UNSUPPORTED_VERSION. Nothing is re-canonicalised into a different object: a wrong owner,
    extra or missing identity key, unknown or unsupported kind each refuse. Out-of-scope and absent Work refuse
    alike (NOT_IN_SCOPE). Returns {'reference': the canonical reference, 'version': {'requested', 'status'}}."""
    problems = identity.reference_problems(value)
    if problems:
        raise DiscoveryRefusal('MALFORMED_REFERENCE', 'Not a reference: ' + '; '.join(problems))
    value = _detached(value)
    kind, ident, owner = value['kind'], value['identity'], value['owner']
    if kind not in _SUPPORTED:
        raise DiscoveryRefusal('UNSUPPORTED_TARGET', 'This owner admits subsystems, declared capabilities and existing Work; '
                               + repr(kind) + ' objects are not supported here.', next_reads=[handle({'facet': 'describe'})])
    keys, responsible = _SUPPORTED[kind]
    if set(ident) != keys:
        raise DiscoveryRefusal('MALFORMED_REFERENCE', 'A %s reference names exactly %s.' % (kind, ', '.join(sorted(keys))),
                               supplied=sorted(ident))
    description = description or _description()
    task = None
    if kind == 'subsystem':
        if owner != responsible:
            raise DiscoveryRefusal('WRONG_OWNER', 'Subsystems are declared by core.identity (the system description).',
                                   supplied=owner, expected=responsible)
        if ident['id'] not in {row['id'] for row in description['subsystems']}:
            raise DiscoveryRefusal('UNKNOWN_TARGET', 'No declared subsystem has this id.', next_reads=[handle({'facet': 'describe'})])
        canonical = identity.reference('core.identity', 'subsystem', {'id': ident['id']})
    elif kind == 'capability':
        declared = {row['id']: row['owner'] for row in description.get('capabilities', [])}
        if ident['id'] not in declared:
            raise DiscoveryRefusal('UNKNOWN_TARGET', 'No declared capability has this id.', next_reads=[handle({'facet': 'describe'})])
        if owner != declared[ident['id']]:
            raise DiscoveryRefusal('WRONG_OWNER', 'This capability is declared with another responsible owner.',
                                   supplied=owner, expected=declared[ident['id']])
        canonical = identity.reference(owner, 'capability', {'id': ident['id']})
    else:
        if owner != responsible:
            raise DiscoveryRefusal('WRONG_OWNER', 'Work is owned by domain.work.', supplied=owner, expected=responsible)
        tasks=(work.read_snapshot(ident['namespace'],root,read_context=read_context,resolve=False)['raw'] if read_context is not None else work._tasks(ident['namespace'],root)) if scope.admits(ident['namespace']) else {}
        task=tasks.get(ident['id'])
        if task is None:
            raise DiscoveryRefusal('NOT_IN_SCOPE', 'No Work matching this reference is readable in the admitted scope.',
                                   next_reads=[handle({'facet': 'describe'})])
        canonical = work_reference(ident['namespace'], ident['id'])
    requested = value.get('version')
    if requested is None:
        return {'reference': canonical, 'version': {'requested': None, 'status': 'UNVERSIONED',
                                                    'says': 'No version was requested; the current object is read.'}}
    if kind != 'work' or set(requested) != {'work_revision'}:
        raise DiscoveryRefusal('UNSUPPORTED_VERSION', 'Only a Work specification revision (version.work_revision) can be '
                               'compared here; this owner keeps no other version history.', requested=requested)
    current = work._task_revision(task)
    if not identity.revision_matches(requested['work_revision'], current):
        now = work_reference(ident['namespace'], ident['id'], revision=current)
        raise DiscoveryRefusal('STALE_VERSION', 'The requested Work revision is not current; the current Work is not '
                               'substituted for it. Read the current reference explicitly.', requested=requested,
                               current={'work_revision': current},
                               next_reads=[handle({'facet': 'inspect', 'reference': now})])
    return {'reference': work_reference(ident['namespace'], ident['id'], revision=current),
            'version': {'requested': requested, 'status': 'CURRENT', 'says': 'The requested revision is the current one.'}}


# ------------------------------------------------------------------------------------------------ the binding fold
_FOLD: dict = {}
_FOLD_LOCK = threading.Lock()


def _bindings(root) -> dict:
    """{(namespace, id): {'current': row, 'history': n}} from the owner's published row tuple (cached on its identity)."""
    rows = work._rows(root)
    with _FOLD_LOCK:
        cached = _FOLD.get(str(work._ledger(root)))
        if cached is not None and cached[0] is rows:
            return cached[1]
    fold: dict = {}
    for row in rows:
        if row.get('record') == BINDING_RECORD:
            key = (row.get('project'), row.get('work_id'))
            fold[key] = {'current': row, 'history': fold.get(key, {}).get('history', 0) + 1}
    with _FOLD_LOCK:
        _FOLD[str(work._ledger(root))] = (rows, fold)
    return fold


def current_binding(root, namespace: str, ident: str) -> dict | None:
    entry = _bindings(root).get((namespace, ident))
    if entry is None:
        return None
    row = entry['current']
    return _detached({'binding_revision': row['binding_revision'], 'relations': row['relations'],
                      'consumed_work_revision': row['consumed_work_revision'], 'prior_binding_revision': row['prior_binding_revision'],
                      'ts': row.get('ts'), 'history': entry['history'], 'by': row.get('by')})


def _description():
    from laplace import system
    return system.load()


def _target(root, description, relation: dict, own_key: str) -> dict:
    """One relation's target, admitted by ``admit_reference`` with the binding author's owned-workspace authority. A
    requested Work version is compared (CURRENT or refused) and not stored: a binding relates objects, not revisions."""
    if relation['relation'] == 'responsible-owner' and (relation['target'] or {}).get('kind') != 'subsystem':
        raise DiscoveryRefusal('UNSUPPORTED_TARGET', 'A responsible owner is a declared subsystem.')
    admitted = admit_reference(root, owned_workspace('binding'), relation['target'], description=description)
    target = {key: admitted['reference'][key] for key in ('schema_version', 'owner', 'kind', 'identity')}
    if identity.reference_key(target) == own_key:
        raise DiscoveryRefusal('UNSUPPORTED_TARGET', 'A Work does not bind to itself.')
    return {'relation': relation['relation'], 'target': target}


def bind(root, payload: dict, *, door: dict) -> dict:
    """Admit one binding for an existing Work through the Work owner's writer, guarded twice (see module doc)."""
    from jsonschema import Draft202012Validator
    payload = _detached(payload)          # the caller keeps its own objects; nothing admitted aliases them
    error = next(Draft202012Validator(binding_contract()).iter_errors(payload), None)
    if error:
        raise ValueError('Binding does not match its owner contract: ' + error.message)
    root = work._root(root)
    namespace, ident = payload['namespace'], payload['id']
    description = _description()
    own_key = identity.reference_key(work_reference(namespace, ident))
    relations = [_target(root, description, item, own_key) for item in payload['relations']]
    keys = [(item['relation'], identity.reference_key(item['target'])) for item in relations]
    if len(set(keys)) != len(keys):
        raise DiscoveryRefusal('DUPLICATE_RELATION', 'Each relation to one target is stated once.')

    def compare():
        task = work._tasks(namespace, root).get(ident)
        if task is None:
            raise DiscoveryRefusal('UNKNOWN_TARGET', 'No existing Work matches this namespace and id.')
        observed = work._task_revision(task)
        if not identity.revision_matches(payload['expected_work_revision'], observed):
            raise work.WorkConflict('Read the exact Work specification before binding it.', namespace, ident,
                                    expected=payload['expected_work_revision'], observed=observed, field='expected_work_revision')
        current = current_binding(root, namespace, ident)
        return task, observed, current

    # Preparation above is early refusal only. Acceptance - publishing or reusing a current binding - is decided
    # inside the ledger's writer lock: the subject's two guards and EVERY original target, re-admitted through
    # admit_reference with its requested version, are compared at the effect itself (a target edited after
    # preparation refuses STALE_VERSION and nothing is appended). Only then is the logical, unversioned target stored.
    _task, observed, _current = compare()
    expected = payload['expected_binding_revision']
    originals = [item['target'] for item in payload['relations']]

    class _AlreadyCurrent(Exception):
        """Raised inside the lock to reuse the current binding: nothing is banked."""

    def admit():
        nonlocal observed
        _task, observed, now = compare()
        for target in originals:
            admit_reference(root, owned_workspace('binding'), target, description=description)
        if now is not None and now['relations'] == relations and now['prior_binding_revision'] == expected \
                and now['consumed_work_revision'] == observed:
            raise _AlreadyCurrent(now)
        held = now['binding_revision'] if now else None
        if held != expected:
            raise work.WorkConflict('The Work binding changed; read its current binding before replacing it.', namespace, ident,
                                    expected=expected, observed=held, field='expected_binding_revision')

    revision = identity.canonical_digest({'project': namespace, 'work_id': ident, 'relations': relations, 'prior': expected})
    row = {'record': BINDING_RECORD, 'kind': 'owner-binding', 'schema_version': BINDING_SCHEMA,
           'id': 'BIND-' + uuid.uuid4().hex, 'project': namespace, 'work_id': ident,
           'ts': dt.datetime.now(dt.timezone.utc).isoformat(), 'relations': relations,
           'consumed_work_revision': observed, 'prior_binding_revision': expected, 'binding_revision': revision,
           'by': payload.get('by') or door.get('origin') or 'owner', 'door': dict(door)}
    try:
        result = work._append(root, row, admit=admit)
    except _AlreadyCurrent as reuse:
        return _detached({'replayed': True, 'binding': reuse.args[0], 'work': work_reference(namespace, ident, revision=observed),
                          'says': 'This exact binding is already current; nothing was appended.'})
    return _detached({'replayed': False, 'binding': current_binding(root, namespace, ident),
                      'work': work_reference(namespace, ident, revision=observed), 'owned_changes': result['owned_changes'],
                      'read': handle({'facet': 'inspect', 'reference': work_reference(namespace, ident)}),
                      'says': 'Binding recorded. It is metadata of this Work: no specification, standing, evidence or authority changed.'})


# ------------------------------------------------------------------------------------------------ reads
def _clip(text, limit=TEXT):
    text = str(text or '')
    return text if len(text) <= limit else text[:limit].rstrip() + '…'


def _envelope(facet, grade, scope, **values):
    return {'schema_version': RESULT_SCHEMA, 'facet': facet, 'grade': grade, 'scope': scope.public(), **values}


def _in_scope(root, scope, *, read_context=None):
    """The in-scope bindings: [(namespace, id, current row)]."""
    return [(namespace, ident, entry['current']) for (namespace, ident), entry in sorted(_bindings(root).items())
            if scope.admits(namespace) and ident in (work.read_snapshot(namespace,root,read_context=read_context,resolve=False)['raw'] if read_context is not None else work._tasks(namespace,root))]


def _touches(row, subsystem, capability_owners):
    matched = []
    for item in row['relations']:
        target = item['target']
        if target['kind'] == 'subsystem' and target['identity']['id'] == subsystem:
            matched.append(item['relation'])
        elif target['kind'] == 'capability' and capability_owners.get(target['identity']['id']) == subsystem:
            matched.append(item['relation'] + ' (capability ' + target['identity']['id'] + ')')
    return matched


def describe(root, scope: Scope, payload: dict) -> dict:
    from laplace import system
    description = _description()
    entry = system.entry(description)
    owners = {row['id']: row['owner'] for row in description.get('capabilities', [])}
    bound = _in_scope(root, scope)
    subsystems = []
    for row in entry['subsystems']:
        ident = row['reference']['identity']['id']
        count = sum(1 for _ns, _id, binding in bound if _touches(binding, ident, owners))
        subsystems.append({'reference': row['reference'], 'layer': row['layer'], 'summary': _clip(row['summary'], 240),
                           'affecting_work': {'bound_in_scope': count},
                           'next': handle({'facet': 'discover', 'subsystem': ident})})
    task = payload.get('task')
    selection = None
    if task is not None:
        found = system.choices(task, description)
        selection = {'task': task, 'choices': [{**item, 'next': handle({'facet': 'discover',
                     'subsystem': item['reference']['identity']['id']})} for item in found],
                     'says': ('No declared subsystem word was named; choose from the subsystems below.' if not found else
                              'Declared subsystems whose words the task names; choose one to descend. Nothing was selected for you.')}
    return _envelope('describe', 'system', scope, purpose=entry['purpose'], selection=selection, subsystems=subsystems,
                     capabilities=entry['capabilities'],
                     coverage={'bound_in_scope': len(bound), 'unbound': UNBOUND,
                               'declarations': 'Subsystem ownership is the system description (laplace.system); which '
                                               'Work affects them is this Work owner\'s bindings.'})


def _cut(scope, rows):
    # what the scope admits, never which door asked: the same facts have one cut on every door
    return identity.canonical_digest({'scope': [scope.kind, scope.namespace], 'rows': rows})


def discover(root, scope: Scope, payload: dict) -> dict:
    description = _description()
    subsystem = payload.get('subsystem')
    known = {row['id']: row for row in description['subsystems']}
    if subsystem not in known:
        raise DiscoveryRefusal('UNKNOWN_SUBSYSTEM', 'Name a declared subsystem; describe lists them.',
                               next_reads=[handle({'facet': 'describe'})])
    owners = {row['id']: row['owner'] for row in description.get('capabilities', [])}
    offset, limit = payload.get('offset', 0), payload.get('limit', PAGE)
    from laplace.work import project_work_views as views
    resolved: dict = {}
    items = []
    for namespace, ident, binding in _in_scope(root, scope):
        matched = _touches(binding, subsystem, owners)
        if not matched:
            continue
        if namespace not in resolved:
            resolved[namespace] = {row['id']: row for row in work._resolved_tasks(work._tasks(namespace, root), root)}
        row = views._public(resolved[namespace][ident], namespace)
        items.append({'reference': work_reference(namespace, ident), 'relations': matched, 'title': row.get('title'),
                      'task_kind': row.get('task_kind'), 'status': row.get('status'), 'lifecycle': row.get('lifecycle'),
                      'readiness': row.get('readiness'), 'current_acceptance': row.get('current_acceptance'),
                      'binding_revision': binding['binding_revision'],
                      'next': handle({'facet': 'inspect', 'reference': work_reference(namespace, ident)})})
    items.sort(key=lambda item: (bool((item['lifecycle'] or {}).get('closed')), item['title'] or ''))
    cut = _cut(scope, [(item['reference']['identity'], item['binding_revision'], item['status'],
                        item['current_acceptance']) for item in items])
    if payload.get('as_of') and payload['as_of'] != cut:
        raise DiscoveryRefusal('CHANGED_INPUT', 'Bindings or standings changed between pages; old pages were not mixed.',
                               next_reads=[handle({'facet': 'discover', 'subsystem': subsystem})])
    page = items[offset:offset + limit]
    more = offset + limit < len(items)
    groups: dict = {}
    for item in items:
        name = 'closed' if (item['lifecycle'] or {}).get('closed') else 'open'
        groups[name] = groups.get(name, 0) + 1
    row = known[subsystem]
    open_titles = [item['title'] for item in items if not (item['lifecycle'] or {}).get('closed')][:3]
    summary = {'subsystem': row['id'], 'bound_in_scope': len(items), 'by_lifecycle': groups,
               'says': ('%d bound Work in scope affect %s; %d open%s.' % (
                   len(items), row['id'], groups.get('open', 0),
                   (': ' + '; '.join(open_titles)) if open_titles else '')) if items else
               'No Work in scope is bound to %s. Unbound Work may still exist.' % row['id'],
               'up': handle({'facet': 'describe'})}
    return _envelope('discover', 'subsystem', scope,
                     subsystem={'reference': {'schema_version': identity.REFERENCE_SCHEMA, 'owner': 'core.identity',
                                              'kind': 'subsystem', 'identity': {'id': row['id']}},
                                'layer': row['kind'], 'summary': _clip(row['summary'], 240),
                                'explanation': list(row.get('explanation') or []),
                                'source_inventory_read':handle({'facet':'source-inventory','reference':identity.reference('core.identity','subsystem',{'id':row['id']})}),
                                # the same inventory owner's bounded inputs-only reads: the declared explanation first, then every input
                                'explanation_read':handle({'facet':'source-inventory','reference':identity.reference('core.identity','subsystem',{'id':row['id']}),
                                                           'projection':'inputs','role':'explanation-source'}) if row.get('explanation') else None,
                                'source_inputs_read':handle({'facet':'source-inventory','reference':identity.reference('core.identity','subsystem',{'id':row['id']}),
                                                             'projection':'inputs'})},
                     items=page, total=len(items), offset=offset, limit=limit,
                     next=handle({'facet': 'discover', 'subsystem': subsystem, 'offset': offset + limit,
                                  'limit': limit, 'as_of': cut}) if more else None,
                     read_cut={'revision': cut, 'scope': 'In-scope bindings and the standings their owner resolved at this read.'},
                     up_summary=summary, coverage={'bound_in_scope': len(items), 'unbound': UNBOUND,
                                                   'truncated': more})


def _scoped_work(root, scope, value) -> tuple[str, str, dict]:
    """(namespace, id, version) of the Work a reference names exactly, through ``admit_reference``; a legacy
    ``namespace::id`` or ``project`` read handle is first resolved (unversioned). Anything else refuses."""
    if isinstance(value, str) or (isinstance(value, dict) and value.get('operation') == 'project'):
        resolved = resolve(root, scope, {'reference': value})
        if resolved['status'] != 'RESOLVED':
            raise DiscoveryRefusal('NOT_IN_SCOPE', 'No Work matching this reference is readable in the admitted scope.',
                                   choices=resolved.get('choices'), next_reads=[handle({'facet': 'describe'})])
        value = resolved['reference']
    admitted = admit_reference(root, scope, value)
    if admitted['reference']['kind'] != 'work':
        raise DiscoveryRefusal('UNSUPPORTED_TARGET', 'inspect opens Work; follow a subsystem with discover.',
                               next_reads=[handle({'facet': 'describe'})])
    found = admitted['reference']['identity']
    return found['namespace'], found['id'], admitted['version']


def _lateral(root, scope, relations):
    out, withheld = [], 0
    for item in relations:
        target = item['target']
        if target['kind'] == 'work':
            namespace, ident = target['identity']['namespace'], target['identity']['id']
            if not scope.admits(namespace):
                withheld += 1
                continue
            row = work._tasks(namespace, root).get(ident) or {}
            out.append({'relation': item['relation'], 'direction': 'outgoing', 'reference': work_reference(namespace, ident),
                        'title': row.get('title'), 'next': handle({'facet': 'inspect', 'reference': work_reference(namespace, ident)})})
        elif target['kind'] == 'subsystem':
            out.append({'relation': item['relation'], 'reference': target,
                        'next': handle({'facet': 'discover', 'subsystem': target['identity']['id']})})
        else:
            out.append({'relation': item['relation'], 'reference': target, 'next': handle({'facet': 'describe'})})
    return out, withheld


def inspect(root, scope: Scope, payload: dict, *, mode: str = 'human') -> dict:
    from laplace.work import project_work_views as views
    namespace, ident, version = _scoped_work(root, scope, payload.get('reference'))
    detail = views.read(namespace, {'view': 'detail', 'id': ident}, root, mode=mode)
    task = detail['task']
    binding = current_binding(root, namespace, ident)
    relations, withheld = _lateral(root, scope, binding['relations'] if binding else [])
    activity = task.get('activity') or {}
    evidence = task.get('evidence_reads') or []
    actions = detail.get('allowed_actions') or {}
    parent = detail.get('parent')
    up = [item for item in relations if item['reference']['kind'] == 'subsystem']
    lateral = [item for item in relations if item['reference']['kind'] != 'subsystem']
    own = identity.reference_key(work_reference(namespace, ident))
    for other_ns, other_id, row in _in_scope(root, scope):     # incoming relations, from in-scope bindings only
        for item in row['relations']:
            if item['target']['kind'] == 'work' and identity.reference_key(item['target']) == own:
                title = (work._tasks(other_ns, root).get(other_id) or {}).get('title')
                lateral.append({'relation': item['relation'], 'direction': 'incoming', 'reference': work_reference(other_ns, other_id),
                                'title': title, 'next': handle({'facet': 'inspect', 'reference': work_reference(other_ns, other_id)})})
    if parent and scope.admits(namespace):
        lateral.append({'relation': 'contained-by', 'reference': work_reference(namespace, parent['id']),
                        'title': parent.get('title'),
                        'next': handle({'facet': 'inspect', 'reference': work_reference(namespace, parent['id'])})})
    return _envelope(
        'inspect', task.get('task_kind') or 'work', scope,
        reference=work_reference(namespace, ident, revision=task.get('work_revision')), version=version,
        title=task.get('title'), purpose=_clip(task.get('goal')), task_kind=task.get('task_kind'),
        standing={'status': task.get('status'), 'recorded_status': task.get('recorded_status'),
                  'facts': (task.get('standing') or {}).get('facts'), 'lifecycle': task.get('lifecycle'),
                  'readiness': task.get('readiness'), 'current_acceptance': task.get('current_acceptance')},
        blockers=[{'relation': item.get('relation'), 'sentence': item.get('sentence'),
                   'next_actions': [action.get('kind') for action in item.get('next_actions') or []]}
                  for item in detail.get('blockers') or []],
        activity={'state': activity.get('state'), 'qualification': activity.get('qualification'),
                  'observations': [{key: item.get(key) for key in ('source', 'subject', 'observed_state', 'observed_at',
                                                                     'expires_at', 'observer', 'current', 'qualification')}
                                   for item in (activity.get('observations') or [])[:3]],
                  'coverage': activity.get('coverage')},
        next={'readiness': (task.get('readiness') or {}).get('status'),
              # an action's own intent_projection travels with it: a field it excludes (a request identity minted per
              # read) is not part of the action's intent, so callers can compare reads without losing any guard
              'actions': [{'name': name, 'permitted': value.get('permitted'), 'http': value.get('http'),
                           'requires': value.get('requires'),
                           **({'intent_projection': value['intent_projection']} if value.get('intent_projection') else {})}
                          for name, value in actions.items()],
              'says': 'Actions run through the Work owner\'s own admitted doors with their exact guards; this read admits none.'},
        evidence={'items': evidence[:EVIDENCE_PAGE], 'total': len(evidence), 'truncated': len(evidence) > EVIDENCE_PAGE,
                  'continuation': task.get('read_handle') if len(evidence) > EVIDENCE_PAGE else None,
                  'says': 'Each item is the Work owner\'s own evidence read (availability, pin, HTTP and native reads or the '
                          'capability gap), read by its own owner, which decides body access; this metadata grants none. '
                          'continuation is the Work detail read carrying every evidence read.'},
        binding=({key: binding[key] for key in ('binding_revision', 'history', 'ts', 'consumed_work_revision')}
                 if binding else None),
        up=up or [{'relation': 'declared', 'reference': None, 'next': handle({'facet': 'describe'}),
                   'says': 'This Work has no owner binding yet; start again from the system entry.'}],
        lateral=lateral,
        legacy={'qualified_id': namespace + '::' + ident, 'read': task.get('read_handle'),
                'history': ((detail.get('reference') or {}).get('history') or {}).get('read')},
        read_cut={'work': detail.get('read_cut'), 'binding_revision': binding['binding_revision'] if binding else None},
        coverage={'children': (detail.get('children') or {}).get('total'),
                  'evidence_truncated': len(evidence) > EVIDENCE_PAGE,
                  'withheld': ('Some relations of this Work lead outside the admitted scope and are not shown.'
                               if withheld else None),
                  'unbound': None if binding else UNBOUND})


def resolve(root, scope: Scope, payload: dict) -> dict:
    value = payload.get('reference')
    candidates: list[tuple[str, str]] = []
    if isinstance(value, dict) and value.get('operation') == 'project':
        inner = value.get('payload') or {}
        candidates = [(inner.get('namespace'), inner.get('id'))]
    elif isinstance(value, dict):
        try:
            admitted = admit_reference(root, scope, value)
        except DiscoveryRefusal as refused:
            return _envelope('resolve', 'reference', scope, status=refused.details['code'], reference=None, says=str(refused),
                             **{key: item for key, item in refused.details.items() if key != 'code'})
        found = admitted['reference']
        nxt = (handle({'facet': 'inspect', 'reference': found}) if found['kind'] == 'work' else
               handle({'facet': 'discover', 'subsystem': found['identity']['id']}) if found['kind'] == 'subsystem' else
               handle({'facet': 'describe'}))
        return _envelope('resolve', 'reference', scope, status='RESOLVED', reference=found, version=admitted['version'], next=nxt)
    elif isinstance(value, str) and '::' in value:
        candidates = [tuple(value.split('::', 1))]
    elif isinstance(value, str) and value:
        candidates = [(namespace, value) for namespace in sorted({row.get('project') for row in work._rows(root)
                      if row.get('record') == 'project-work' and row.get('project')}) if scope.admits(namespace)]
    else:
        raise DiscoveryRefusal('MALFORMED_REFERENCE', 'Supply a reference, a namespace::id or a project read handle.')
    found = [(namespace, ident) for namespace, ident in candidates
             if isinstance(namespace, str) and scope.admits(namespace) and ident in work._tasks(namespace, root)]
    if len(found) == 1:
        namespace, ident = found[0]
        return _envelope('resolve', 'reference', scope, status='RESOLVED', reference=work_reference(namespace, ident),
                         version={'requested': None, 'status': 'UNVERSIONED', 'says': 'A legacy handle names no version; the current Work is read.'},
                         next=handle({'facet': 'inspect', 'reference': work_reference(namespace, ident)}))
    if len(found) > 1:
        return _envelope('resolve', 'reference', scope, status='AMBIGUOUS',
                         choices=[{'reference': work_reference(namespace, ident),
                                   'next': handle({'facet': 'inspect', 'reference': work_reference(namespace, ident)})}
                                  for namespace, ident in found],
                         says='Several readable namespaces hold this local id; choose one. Local ids are not global.')
    return _envelope('resolve', 'reference', scope, status='NOT_IN_SCOPE', reference=None,
                     says='No Work matching this reference is readable in the admitted scope.',
                     next=handle({'facet': 'describe'}))


def request(root, scope: Scope, payload: dict, *, mode: str = 'human') -> dict:
    """The one read door: validate the shared request contract, then exactly one facet."""
    from jsonschema import Draft202012Validator
    if not isinstance(scope, Scope):
        raise TypeError('The adapter supplies the caller scope.')
    payload = _detached(payload)
    error = next(Draft202012Validator(contract()).iter_errors(payload), None)
    if error:
        raise ValueError('Discovery request does not match its owner contract: ' + error.message)
    root = work._root(root)
    facet = payload.get('facet', 'describe')
    reference = payload.get('reference')
    if facet=='source-kernel':
        from laplace.work import source_kernel
        return _detached(source_kernel.read(root,scope,payload))
    if facet=='historical-obligations':
        from laplace.engine import historical_obligations
        return _detached(historical_obligations.read(root,scope,payload))
    if facet=='source-inventory':
        from laplace.work import source_inventory
        return _detached(source_inventory.read(root,scope,payload))
    if facet=='source-input':
        # one declared row's bounded body; the inventory owner refuses every scope except the owned workspace HTTP door
        from laplace.work import source_inventory
        return _detached(source_inventory.read_input(root,scope,payload))
    if facet in {'neighbourhood','semantic-scope','timeline'}:
        if facet=='timeline' and not isinstance(reference,dict):raise ValueError('Timeline selects an exact owner reference.')
        from laplace.work import object_geometry
        return _detached(object_geometry.request(root,scope,payload,read_context={}))
    if facet in {'workspace','object','dependents','handover','input','object-request','manuscript-selection'}:
        from laplace.work import object_facets
        return _detached(object_facets.request(root,scope,payload))
    if facet == 'inspect' and isinstance(reference, dict) and reference.get('kind') == 'source-contract':
        # the supported source-contract read (work.source_contracts): owner + operation identity, read in the caller's
        # scope (publications and reviews of other namespaces are not seen); one normalized request before any branch
        from laplace.work import source_contracts
        try:
            return source_contracts.read(root, source_contracts.normalize(reference, select=payload.get('select'), budget=payload.get('budget')),
                                         admits=scope.admits, read_scope=scope)
        except source_contracts.Refusal as error:
            raise DiscoveryRefusal(error.details['code'], str(error), **{k: v for k, v in error.details.items() if k != 'code'}) from None
    if 'select' in payload or 'budget' in payload:
        raise ValueError('select and budget belong to a source-contract inspect.')
    read = {'describe': describe, 'discover': discover, 'resolve': resolve}.get(facet)
    value = read(root, scope, payload) if read else inspect(root, scope, payload, mode=mode)
    return _detached(value)     # no returned object, however nested, is the owner's cached row
