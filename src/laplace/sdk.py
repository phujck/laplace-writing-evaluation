"""laplace.sdk: the installed Python entry to the system's owners (adapter.sdk).

Start at the system and follow what it returns; no project name, Work id or file path is needed to begin:

    from laplace import sdk
    entry = sdk.describe(task='find current work affecting the browser/workflow interface')
    chosen = entry['selection']['choices'][0]['next']['request']   # a declared subsystem, chosen by the caller
    page = sdk.request(chosen)                                     # the Work bound to it, with standing
    work = sdk.request(page['items'][0]['next']['request'])        # purpose, activity, next, evidence, lateral

Every result carries the next reads as ``next`` / ``up`` / ``lateral`` handles. ``handle['request']`` is what
``request`` takes; the same request is the native Work read ``project {"view": "discovery", "request": ...}`` and
``GET /work/discovery``.

Authority. This entry reads the local owned workspace of ``root`` (``laplace.core.checkout.repo_root()`` when
omitted) with that root's own authority: it is a local library, not a remote or multi-tenant service. ``bind``
records an owner binding through the Work owner with its two guards. Discovery and preparation do not start a
provider. The explicit ``reader_start`` entry requests a fresh qualified reader through ordinary turn admission;
it grants no source edit, workflow launch or Work standing change.

This module composes owners and adds no rule of its own: the system entry is ``laplace.system`` (core.identity),
the Work facts are ``laplace.work.owner_discovery`` (domain.work).
"""
from __future__ import annotations

from pathlib import Path

__all__ = ['source_inventory','source_kernel','historical_obligations','describe', 'discover', 'inspect', 'resolve', 'request', 'bind', 'contract', 'binding_contract', 'source_contract', 'workflow_request', 'workflow_save', 'workflow_prepare', 'workflow_restore', 'reader_request', 'reader_start', 'conversation_message', 'material_intake_request', 'material_intake_upload', 'material_intake_link', 'research_object', 'research_object_change', 'research_handover']


def _root(root) -> Path:
    from laplace.core import checkout
    return Path(root).resolve() if root else checkout.repo_root()


def _scope():
    from laplace.work import owner_discovery
    return owner_discovery.owned_workspace('sdk')


def contract() -> dict:
    from laplace.work import owner_discovery
    return owner_discovery.contract()


def binding_contract() -> dict:
    from laplace.work import owner_discovery
    return owner_discovery.binding_contract()


def request(payload: dict, *, root=None) -> dict:
    """One discovery read (``contract()``), using a discovery handle's ``request``.

    Project Work handles use ``work_read(handle['payload'])`` instead.
    """
    from laplace.work import owner_discovery
    return owner_discovery.request(_root(root), _scope(), dict(payload))


def describe(task: str | None = None, *, root=None) -> dict:
    """The system grade: purpose, subsystem and capability references, and the task's declared-word choices."""
    return request({'facet': 'describe', **({'task': task} if task is not None else {})}, root=root)


def discover(subsystem: str, *, offset: int = 0, limit: int | None = None, as_of: str | None = None, root=None) -> dict:
    """The subsystem grade: the bound Work affecting one declared subsystem, paged under a read cut."""
    payload = {'facet': 'discover', 'subsystem': subsystem, 'offset': offset}
    if limit is not None:
        payload['limit'] = limit
    if as_of is not None:
        payload['as_of'] = as_of
    return request(payload, root=root)


def inspect(reference, *, root=None) -> dict:
    """The Work grade of one returned reference (or a legacy ``namespace::id`` / ``project`` read handle)."""
    return request({'facet': 'inspect', 'reference': reference}, root=root)


def source_inventory(reference: dict, *, offset: int = 0, limit: int | None = None,
                     as_of: str | None = None, project_lens: str | None = None,
                     projection: str | None = None, root=None):
    """Bounded declared source inputs of an exact subsystem; no body/kernel lookup or effects.

    Follow discover(...).subsystem.source_inventory_read or pass its exact
    core.identity subsystem reference. Source pins are not acceptance or ingestion.
    """
    payload={'facet':'source-inventory','reference':reference,'offset':offset}
    if limit is not None:payload['limit']=limit
    if as_of is not None:payload['as_of']=as_of
    if project_lens is not None:payload['project_lens']=project_lens
    if projection is not None:payload['projection']=projection
    return request(payload,root=root)

__all__.append('source_inventory')


def source_kernel(reference: dict | None = None, *, selection=None, view='publications', segments=None, namespace=None, budget=None, root=None):
    """Explicit retained Source publications/preparation/counterpart; pure reads never ingest."""
    payload={'facet':'source-kernel','view':view}
    if reference is not None:payload['reference']=reference
    if namespace is not None:payload['namespace']=namespace
    if selection is not None:payload['selection']=selection
    if segments is not None:payload['segments']=segments
    if budget is not None:payload['budget']=budget
    return request(payload,root=root)


def source_publication(payload: dict, *, root=None):
    """Explicit local operator preparation/commit/recovery over active publication custody.

    This is trusted local SDK authority, not a native read grant. Exact prepared
    inputs and expected publication basis come from the publication owner.
    """
    from laplace.representation import source_publication as owner
    return owner.request(_root(root), _scope(), dict(payload))


__all__.append('source_publication')


def historical_obligations(source: str, *, state='open', offset=0, limit=20, as_of=None, root=None):
    """Selected historical engine source, root SDK only; separate from canonical Work."""
    payload={'facet':'historical-obligations','source':source,'state':state,'offset':offset,'limit':limit}
    if as_of is not None:payload['as_of']=as_of
    return request(payload,root=root)


def resolve(reference, *, root=None) -> dict:
    """A reference, legacy ``namespace::id`` or legacy read handle to the canonical reference, or choices."""
    return request({'facet': 'resolve', 'reference': reference}, root=root)


def bind(payload: dict, *, root=None) -> dict:
    """Record an owner binding for an existing Work (``binding_contract()``), guarded by its specification and binding
    revisions; a replay of the current binding appends nothing."""
    from laplace.work import owner_discovery
    return owner_discovery.bind(_root(root), dict(payload), door={'origin': 'sdk'})


def source_contract(operation: str | None = None, select: str | None = None, *, version: str | None = None, reference: dict | None = None,
                    budget: int | None = None, root=None) -> dict:
    """An operation's source contract through the owner-discovery read (``request`` facet inspect, kind source-contract):
    ``reference`` (its registered owner, kind source-contract, identity {operation}, optional version {declaration}) or
    ``operation`` ('domain.work:work_review.followup') with optional ``version``. Unversioned: the current declaration
    with each consumer's canonical standing. Explicit version: exactly that retained version, refused when not retained.
    ``select`` ('step:<id>' / 'segment:<id>') and ``budget`` (bytes, the whole returned envelope) apply to both. With
    neither operation nor reference: the declared operations, within the budget. Reads only; detached JSON."""
    from laplace.work import source_contracts
    if operation is None and reference is None:
        return source_contracts.listing(budget=budget)
    if reference is None:
        owner, _, name = operation.partition(':')
        reference = source_contracts.reference(owner, name, version)
    elif version is not None:
        raise ValueError('CONFLICTING_VERSION: name the version inside the reference or as version=, not both.')
    payload = {'facet': 'inspect', 'reference': reference, **({'select': select} if select is not None else {}),
               **({'budget': budget} if budget is not None else {})}
    return request(payload, root=root)


def workflow_request(payload=None, *, root=None):
    """Read owner-scoped definitions and issued bounded history/lineage/saved-body pages.

    Follow each exact returned request. Fixed prefix/current head and read-only saved
    version are separate; legacy v1 export retains its original bounds.
    """
    from laplace.pipeline import workflow_definitions
    selected=_root(root);scope=_scope();payload=dict(payload or {})
    if 'project_lens' in payload:
        from laplace.pipeline import registry
        from laplace.work import owner_discovery
        lens=payload['project_lens']
        if not isinstance(lens,str) or lens not in registry.all_projects(repo_root=selected):raise ValueError('Project lens is unavailable in this owned workspace.')
        scope=owner_discovery.project_scope(lens,'sdk')
    return workflow_definitions.read(selected, scope, payload)


def workflow_save(payload, *, root=None):
    """Save an immutable definition version; does not prepare or start a run."""
    from laplace.pipeline import workflow_definitions
    return workflow_definitions.save(_root(root), _scope(), payload)


def workflow_prepare(payload, *, root=None):
    """Prepare a supported exact saved slice through the existing carrier; never start."""
    from laplace.pipeline import workflow_definitions
    return workflow_definitions.prepare(_root(root), _scope(), payload)


def workflow_withdraw(payload, *, root=None):
    """Withdraw one exact unadmitted Save/Prepare request through its original owner.

    A recorded winner returns its retained receipt; UNKNOWN remains unresolved.
    This does not undo a saved version, preparation or already-admitted execution.
    """
    from laplace.pipeline import workflow_definitions
    return workflow_definitions.withdraw(_root(root), _scope(), dict(payload))


def workflow_restore(payload, *, root=None):
    """Restore exported exact identities/history into this local root's existing custody."""
    from laplace.pipeline import workflow_definitions
    return workflow_definitions.restore(_root(root), _scope(), payload)


def reader_request(payload, *, root=None):
    """Inspect/prepare exact text intake through the session input owner; never infer."""
    from laplace.writing import sealed_reader
    return sealed_reader.request(_root(root),dict(payload))


def reader_start(payload, *, root=None):
    """Explicit fresh sealed-reader Start through existing turn admission, qualification required."""
    from laplace.writing import sealed_reader, turn_admission
    sealed_reader.start_request(dict(payload))
    return turn_admission.start_turn(_root(root),dict(payload))


def reader_deliberate(payload, *, root=None):
    """Explicit ordinary bounded document deliberation (purpose document-deliberation) through existing admission.

    Preview first with ``reader_request({'project', 'view': 'deliberation-preview', 'commission'})``; this Start
    revalidates QUALIFIED support, supported limits, exact input/settings and the immutable request intent.
    """
    from laplace.writing import turn_admission
    return turn_admission.start_reader_deliberation(_root(root),dict(payload))


__all__.append('reader_deliberate')


def conversation_message(payload, *, root=None):
    """Read one exact saved request/displayed reply part; no admission or rich turn read."""
    from laplace.writing import session_reads
    return session_reads.public_message(_root(root),dict(payload))


def material_intake_request(project: str, payload: dict | None = None, *, root=None) -> dict:
    """Pure local intake describe/status; no file selection, provider or effects."""
    from laplace.projects import material_intake
    payload={} if payload is None else dict(payload)
    if not payload or payload=={'view':'describe'}:return material_intake.describe(_root(root),project)
    if set(payload)=={'view','request_id'} and payload['view']=='status':return material_intake.status(_root(root),project,payload['request_id'])
    raise ValueError('Choose describe or exact request status.')


def material_intake_upload(project: str, metadata: dict, raw: bytes, *, root=None) -> dict:
    """Explicit local owned-workspace upload of bounded supplied bytes; same owner as human HTTP."""
    from laplace.projects import material_intake
    return material_intake.upload(_root(root),project,metadata,raw)


def material_intake_link(project: str, request_id: str, expected_revision: str, *, root=None) -> dict:
    """Explicit recovery of retained original receipt/membership, without re-upload."""
    from laplace.projects import material_intake
    return material_intake.link(_root(root),project,{'request_id':request_id,'expected_revision':expected_revision})


def research_object(payload, *, root=None):
    """Workspace/selected-object facets via the existing owner discovery boundary."""
    return request(dict(payload),root=root)


def research_object_change(payload, *, root=None):
    """Explicit local-operator object effect through existing canonical owners."""
    from laplace.work import object_facets,owner_discovery
    return object_facets.change(_root(root),owner_discovery.owned_workspace('sdk'),dict(payload),door={'origin':'sdk'})


def research_handover(payload, *, root=None):
    """Select/inspect/export permitted frozen object closure through its owner.

    The opt-in lineage-v2 request issues an exact source-bound export wire before
    effects. Keep it across PARTIAL/UNKNOWN; only issued checkpoint-bound Continue
    advances a verified quiescent stage. Local SDK authority does not travel.
    """
    from laplace.projects import project_handover
    from laplace.work import owner_discovery
    return project_handover.object_request(_root(root),owner_discovery.owned_workspace('sdk'),dict(payload),door={'origin':'sdk'})


def session_settings_request(project: str, payload: dict, *, root=None):
    """Read/save/reconcile/withdraw scoped future preferences with local root authority."""
    from laplace.writing import session_settings
    return session_settings.request(_root(root),project,dict(payload),door={'origin':'sdk'})


__all__.append('session_settings_request')


def work_catalogue(payload=None, *, root=None):
    """Complete all-namespace Work catalogue; bounded owner search/filter/read cut."""
    from laplace.work import project_work
    return project_work.read("", {"view": "catalogue", **dict(payload or {})}, _root(root))


def work_read(payload: dict, *, root=None) -> dict:
    """Follow an issued project Work handle's exact readonly ``payload``.

    This local SDK reads its root's owned workspace. It does not carry that
    authority into native callers, accept effect actions, or reinterpret a Work
    payload as owner discovery. Discovery handles still use ``request``.
    """
    from laplace.work import project_work_views
    views = {'summary', 'detail', 'graph', 'full', 'namespaces', 'workflows',
             'queue', 'review', 'roots', 'branch', 'attention', 'group', 'observe',
             'history', 'catalogue', 'planning', 'planning-request',
             'review-evidence', 'provenance', 'continuity'}
    if not isinstance(payload, dict) or payload.get('view') not in views:
        raise ValueError('Select an issued readonly project Work view payload.')
    return project_work_views.read('', dict(payload), _root(root), mode='human',
                                   native_caller=_scope())


def work_plan(project, payload, *, root=None):
    """Explicit guarded planning only, under existing Work custody; starts no work."""
    from laplace.work.backlog import change
    return change(project, dict(payload), _root(root))

__all__.extend(["work_catalogue", "work_read", "work_plan"])


def work_continuity(namespace: str, work_id: str, request: dict | None = None, *, root=None) -> dict:
    """One selected Work's continuity (goal, standing, production, completion, review, delivery, issued next action).

    The exact handle comes from the Work owner (``project_work_continuity.handle``); this is ``work_read`` of its
    payload under the local owned-workspace Scope, which the owner admits before any lookup.
    """
    from laplace.work import project_work_continuity
    return work_read(project_work_continuity.handle(namespace, work_id, request)['payload'], root=root)


def programme(request: dict | None = None, *, root=None) -> dict:
    """The explicitly authored current programme from Eigen records: the session-memory coordinate and, when one is
    SELECTED, its canonical Work continuity through the same owner as every other door. Nothing is read from a client
    transcript, reminder or compatibility current.json."""
    from laplace.engine import session_memory
    selected = _root(root)
    pointer = session_memory.programme(selected)
    out = {'schema_version': 'laplace.sdk-programme/1', 'pointer': pointer}
    if pointer.get('state') == 'SELECTED':
        reference = pointer['reference']
        out['continuity'] = work_continuity(reference['namespace'], reference['work_id'], request, root=selected)
    return out


#: the owner-issued continuity actions this local facade carries; every other effect keeps its own door
_CONTINUITY_ACTIONS = {('work_delivery', 'continue'), ('development_source', 'proof')}


def work_action(project: str, action: dict, *, root=None) -> dict:
    """Invoke ONE owner-issued continuity action (a ``next.action`` of the continuity read) with local operator authority.

    Only an issued Continue (``work_delivery continue``) or a declared peer-proof arrival (``development_source
    proof``) is carried; the effect owner revalidates its basis, account, Stop and recipient at the effect boundary.
    This is not a generic executor: it claims no native origin, grants no publication and arms nothing (only the
    genuine active Source producer arms a completion).
    """
    if not isinstance(action, dict) or set(action) - {'operation', 'payload', 'http'}:
        raise ValueError('Pass one owner-issued action object {operation, payload}.')
    operation, payload = action.get('operation'), action.get('payload')
    if not isinstance(payload, dict) or (operation, payload.get('action')) not in _CONTINUITY_ACTIONS:
        raise ValueError('The SDK continuity facade carries only an issued work_delivery continue or development_source proof; '
                         'other effects keep their own owner doors.')
    if not isinstance(project, str) or not project or payload.get('project', project) != project:
        raise ValueError('The issued action belongs to another project.')
    from laplace.work import development_source, work_delivery
    owner = work_delivery if operation == 'work_delivery' else development_source
    return owner.handle(_root(root), project, {**payload, 'project': project}, {'origin': 'sdk'})


__all__.extend(['work_continuity', 'programme', 'work_action'])
