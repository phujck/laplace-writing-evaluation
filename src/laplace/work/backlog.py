"""The existing Work owner's workspace catalogue and independent planning metadata.

Truth remains in project_work's ledger. A plan is not a task specification,
completion occurrence, prerequisite, execution permission or registered project.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import heapq
import json
import uuid
from urllib.parse import urlencode

CATALOGUE = 'laplace.work-catalogue/1'
REQUEST = 'laplace.work-planning-request/1'
CAP = 28672
DEFAULT = {'priority': 0, 'order': 0, 'deferred': False, 'reason': ''}


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def planning_contract():
    return {'type': 'object', 'required': list(DEFAULT), 'properties': {
        'priority': {'type': 'integer', 'minimum': -1000, 'maximum': 1000},
        'order': {'type': 'integer', 'minimum': -1000000000, 'maximum': 1000000000},
        'deferred': {'type': 'boolean'}, 'reason': {'type': 'string', 'maxLength': 2000}}, 'additionalProperties': False}


def change_contract():
    return {'type': 'object', 'required': ['action', 'id', 'request_id', 'expected_work_revision', 'expected_planning_revision', 'planning'],
            'properties': {'action': {'const': 'planning'}, 'id': {'type': 'string', 'minLength': 1},
                'request_id': {'type': 'string', 'minLength': 8, 'maxLength': 96},
                'expected_work_revision': {'type': 'string', 'pattern': '^sha256:[a-f0-9]{64}$'},
                'expected_planning_revision': {'type': 'string', 'pattern': '^sha256:[a-f0-9]{64}$'},
                'planning': planning_contract()}, 'additionalProperties': False}


def value(row):
    return copy.deepcopy(row.get('planning') or DEFAULT)


def revision(project, row):
    return row.get('planning_revision') or digest({'project': project, 'id': row['id'], 'planning': 'unplanned'})


def projection(project, row):
    return {**value(row), 'authored': 'planning' in row, 'revision': revision(project, row),
            'meaning': 'Authored preference only; readiness, prerequisites, completion and execution authority are separate.'}


ORDERING_VERSION='laplace.work-display-order/2'


def preferred(rows, *, _dependencies=None):
    """Stable preference among available nodes, with real prerequisites first.

    Legacy records have one neutral key and retain first-specification order.
    Cycles are retained in original order; existing Work diagnostics explain them.
    """
    by = {r['id']: r for r in rows}; position = {r['id']: n for n, r in enumerate(rows)}
    degree = {k: 0 for k in by}; after = {k: [] for k in by}
    for ident, row in by.items():
        for dep in dict.fromkeys((row.get('depends_on') or []) if _dependencies is None else _dependencies[ident]):
            if dep in by and (dep != ident or _dependencies is not None):
                degree[ident] += 1; after[dep].append(ident)
    def key(ident):
        plan = value(by[ident])
        return (plan['deferred'], -plan['priority'], plan['order'], position[ident], ident)
    queue = [key(k) for k in by if degree[k] == 0]; heapq.heapify(queue); ordered = []
    while queue:
        ident = heapq.heappop(queue)[-1]; ordered.append(ident)
        for child in after[ident]:
            degree[child] -= 1
            if not degree[child]: heapq.heappush(queue, key(child))
    done = set(ordered)
    return [by[k] for k in ordered] + [r for r in rows if r['id'] not in done]


def display_preferred(full_rows, displayed_rows):
    """Order a display projection, retaining necessary visible precedence.

    Eligibility comes from the unchanged full Work graph. A hidden prerequisite
    stops this traversal ONLY when the Work owner says it actually satisfies
    prerequisites. Hidden unmet nodes remain blockers and connect their visible
    necessary ancestors. This function changes no row, standing or permission.
    """
    full={row['id']:row for row in full_rows};visible={row['id'] for row in displayed_rows}
    if visible==set(full):return preferred(displayed_rows)  # exact legacy/all-view ordering
    projected={}
    for row in displayed_rows:
        required=set();visited=set();active=set();cycle=False
        pending=[(ident,False) for ident in reversed(row.get('depends_on') or [])]
        while pending:
            ident,leaving=pending.pop()
            if leaving:
                active.discard(ident);continue
            if ident in visible:
                required.add(ident);continue
            prior=full.get(ident)
            if prior is None or (prior.get('readiness') or {}).get('satisfies_prerequisites') is True:continue
            if ident in active:
                cycle=True;continue
            if ident in visited:continue
            visited.add(ident);active.add(ident);pending.append((ident,True))
            pending.extend((dep,False) for dep in reversed(prior.get('depends_on') or []))
        if cycle:required.add(row['id']) # keep cyclic display subjects in the stable fallback
        projected[row['id']]=required
    return preferred(displayed_rows,_dependencies=projected)


def request_read(project, ident, request_id):
    from laplace.work.project_work_views import handle
    return handle(project, {'view': 'planning-request', 'id': ident, 'request_id': request_id})


def action(project, row, *, permitted=True):
    from laplace.work.project_work_views import handle
    values = value(row); rid = 'PLAN-' + uuid.uuid4().hex
    fields = [{'name': 'planning.priority', 'label': 'Priority (higher first)', **planning_contract()['properties']['priority'], 'required': True},
              {'name': 'planning.order', 'label': 'Preferred order (lower first)', **planning_contract()['properties']['order'], 'required': True},
              {'name': 'planning.deferred', 'label': 'Deferred intent', 'type': 'boolean', 'required': True},
              {'name': 'planning.reason', 'label': 'Planning or deferral reason', 'type': 'textarea', 'maxLength': 2000, 'required': False}]
    return {'id': 'work-planning', 'title': 'Save planning', 'permitted': permitted, 'operation': 'task',
            'native_context': {'project': project, 'requires_selected_namespace': True},
            'payload': {'action':'planning','id':row['id'],'request_id':rid,'expected_work_revision':row.get('work_revision'),'expected_planning_revision':revision(project,row),'planning':copy.deepcopy(values)},
            'http': {'method': 'POST', 'url': '/work/task', 'payload': {'project': project, 'action': 'planning', 'id': row['id'],
                'request_id': rid, 'expected_work_revision': row.get('work_revision'),
                'expected_planning_revision': revision(project, row), 'planning': values}},
            'fields': fields, 'request_read': request_read(project, row['id'], rid),
            'reconcile': request_read(project, row['id'], rid), 'new_decision_read': planning_read(project,row['id']),
            'intent_projection': {'algorithm': 'sha256-canonical-json-utf8', 'excluded_fields': ['request_id']},
            'authority': 'Existing scoped task writer only. Planning never starts work or grants permission.'}


def _intent(project, payload):
    return {'project': project, **{k: copy.deepcopy(v) for k, v in payload.items() if k not in {'project', 'request_id'}}}


def _history(row):
    history = row.get('planning_history') or ()
    if not isinstance(history,(tuple,list)):raise ValueError('Planning request custody is unsupported.')
    for entry in history:
        if not isinstance(entry,dict) or entry.get('project')!=row.get('project') or entry.get('work_id')!=row.get('id') or entry.get('effect') not in {'RECORDED','NOT_ADMITTED'}:raise ValueError('Planning request custody belongs to another Work or unsupported outcome.')
        if entry.get('kind') != 'work-planning' or not isinstance(entry.get('original_request'), dict):
            raise ValueError('Planning request custody is unsupported.')
        if entry.get('request_id')!=entry['original_request'].get('request_id') or entry['original_request'].get('id')!=row['id'] or entry['original_request'].get('project')!=row['project']:raise ValueError('Planning request identity does not match its Work.')
        if entry.get('intent_digest') != digest({k: v for k, v in entry['original_request'].items() if k != 'request_id'}):
            raise ValueError('Planning request custody does not match its retained intent.')
    return history


def _receipt(project, row, entry, *, replayed=False, mode="human", planning_permitted=True):
    from laplace.work.project_work_views import handle
    from laplace.work import project_work as work
    return {'schema_version': REQUEST, 'project': project, 'work_id': row['id'], 'request_id': entry['request_id'],
            'effect': entry['effect'], 'terminal': True, 'durable': True, 'replayed': replayed,
            'intent_digest': entry['intent_digest'], 'original_request': copy.deepcopy(entry['original_request']),
            'receipt': {k: copy.deepcopy(entry.get(k)) for k in ('id', 'ts', 'planning', 'planning_revision', 'noop', 'reason', 'observed_work_revision', 'observed_planning_revision')},
            'read': request_read(project, row['id'], entry['request_id']),
            'current_read': planning_read(project,row['id']),
            'current': {'project': project, 'namespace': project, 'id': row['id'], 'work_id': row['id'], 'title': row.get('title'), 'planning': projection(project, row),
                        'actions': {'planning': action(project,{**row,'work_revision':work._task_revision(row)},permitted=mode!='review' and planning_permitted)}},
            'current_scope': 'Planning observation only; exact Work detail separately observes current evidence and execution.'}


def inspect_request(project, ident, request_id, root, *, mode="human", planning_permitted=True):
    from laplace.work import project_work as work
    result = {'schema_version': REQUEST, 'project': project, 'work_id': ident, 'request_id': request_id, 'terminal': False}
    try:
        row = work._tasks(project, root).get(ident)
        if not row: raise ValueError('The selected Work is unavailable.')
        matches = [r for r in _history(row) if r.get('request_id') == request_id]
        if len(matches) > 1: raise ValueError('Planning request custody is ambiguous.')
        return _receipt(project, row, matches[0], replayed=True,mode=mode,planning_permitted=planning_permitted) if matches else {**result, 'effect': 'NONE', 'read': request_read(project, ident, request_id)}
    except (ValueError, OSError, TypeError, KeyError) as error:
        return {**result, 'effect': 'UNKNOWN', 'reason': str(error)}


class _Replay(Exception):
    def __init__(self, result): self.result = result


def change(project, payload, root):
    from jsonschema import Draft202012Validator
    from laplace.work import project_work as work
    wire = {'project': project, **copy.deepcopy(payload)}
    if wire['project'] != project: raise ValueError('Planning belongs to another namespace.')
    body = {k: v for k, v in wire.items() if k != 'project'}
    error = next(Draft202012Validator(change_contract()).iter_errors(body), None)
    if error: raise ValueError('Planning request does not match its closed owner contract.')
    ident = body['id']; intent = digest(_intent(project, body))
    with work.dispatch_lock(root):
        row = {'record': 'project-work-phase', 'kind': 'work-planning', 'project': project, 'work_id': ident,
               'id': 'PLANNING-' + uuid.uuid4().hex, 'ts': dt.datetime.now(dt.timezone.utc).isoformat(),
               'request_id': body['request_id'], 'original_request': wire, 'intent_digest': intent}
        def admit():
            tasks = work._tasks(project, root); current = tasks.get(ident)
            if not current: raise ValueError('Exact existing Work is required; planning never creates or registers it.')
            matches = [r for r in _history(current) if r.get('request_id') == body['request_id']]
            if len(matches) > 1: raise ValueError('Planning request custody is ambiguous.')
            if matches:
                if matches[0]['intent_digest'] != intent: raise ValueError('Request ID already records another planning intent.')
                raise _Replay(_receipt(project, current, matches[0], replayed=True))
            wr = work._task_revision(current); pr = revision(project, current)
            row.update(observed_work_revision=wr, observed_planning_revision=pr)
            if body['planning']['deferred'] and not body['planning']['reason'].strip():
                row.update(effect='NOT_ADMITTED', reason='DEFER_REASON_REQUIRED: deferred intent requires an authored reason.')
            elif body['expected_work_revision'] != wr or body['expected_planning_revision'] != pr:
                row.update(effect='NOT_ADMITTED', reason='CHANGED_INPUT: inspect current Work and planning before a new decision.')
            else:
                noop = 'planning' in current and value(current) == body['planning']
                row.update(effect='RECORDED', planning=copy.deepcopy(body['planning']), noop=noop,
                           planning_revision=pr if noop else digest({'planning': body['planning'], 'occurrence': row['id']}))
        try:
            work._append(root, row, admit=admit)
        except _Replay as replay:
            return replay.result
        except OSError:
            return inspect_request(project, ident, body['request_id'], root)
        current = work._tasks(project, root)[ident]
        # The journal owns the canonical stamp; first ACK and later replay must
        # expose the identical retained receipt, not our pre-bank timestamp.
        retained=next(item for item in _history(current) if item['request_id']==body['request_id'])
        return _receipt(project, current, retained)


def planning_read(project, ident):
    from laplace.work.project_work_views import handle
    return handle(project, {'view':'planning','id':ident})


def inspect_planning(project, ident, root, *, mode='human'):
    from laplace.work import project_work as work
    from laplace.work.project_work_views import handle
    row=work._tasks(project,root).get(ident)
    if not row:raise ValueError('Exact existing Work is required for planning.')
    _history(row)  # unsupported retained custody is never replaced by a new form
    selected={**row,'work_revision':work._task_revision(row)}
    return {'schema_version':'laplace.work-planning/1','project':project,'namespace':project,'id':ident,
        'qualified_id':project+'::'+ident,'title':row.get('title','')[:512],'title_complete':len(row.get('title',''))<=512,
        'work_revision':selected['work_revision'],'planning':projection(project,row),
        'actions':{'planning':action(project,selected,permitted=mode!='review')},
        'read':planning_read(project,ident),'detail_read':handle(project,{'view':'detail','id':ident}),
        'scope':'Current Work specification and planning only; readiness, evidence and execution are inspected separately.'}


def catalogue_handle(query=None):
    fields = {'view': 'catalogue', **(query or {})}
    return {'operation': 'project', 'payload': fields, 'http': {'method': 'GET', 'url': '/work/state?' + urlencode(fields)}}


def catalogue(root, query, *, mode="human", caller_project=None):
    from laplace.work import project_work as work, project_work_views as views, owner_discovery
    if mode!='human' and (not caller_project or query.get('namespace',caller_project)!=caller_project):raise ValueError('Work catalogue is outside the actual native project scope.')
    root = work._root(root); rows = views._snapshot(root); registered = views._registered(root)
    permitted = sorted({r['project'] for r in rows if r.get('project') and r.get('record') in {'project-work', 'project-work-transition'} and (mode=='human' or r['project']==caller_project)})
    selected_namespace=query.get('namespace') or (caller_project if mode!='human' else None)
    namespaces=[p for p in permitted if not selected_namespace or p==selected_namespace]
    context = {}; allrows = []; namespace_rows = []
    for project in namespaces:
        snap = views.read_snapshot(project, root, read_context=context)
        namespace_rows.append({'id': project, 'registered': project in registered, 'work_count': len(snap['raw'])})
        for r in snap['resolved']: allrows.append((project, r))
    def matches(project, row):
        if query.get('namespace') and query['namespace'] != project: return False
        if query.get('lifecycle_group')=='unfinished' and row.get('recorded_status') not in {'open','ready','blocked','in-progress'}:return False
        text = query.get('q', '').casefold().strip()
        if text and text not in (project + '::' + row['id'] + '\n' + row.get('title', '') + '\n' + row.get('goal', '')).casefold(): return False
        for key, actual in [('lifecycle', row.get('recorded_status')), ('currentness', row['current_acceptance']['status']), ('readiness', row['readiness']['status'])]:
            if query.get(key) and query[key] != actual: return False
        state = query.get('planning_filter')
        return not state or {'deferred': value(row)['deferred'], 'not-deferred': not value(row)['deferred'], 'planned': 'planning' in row, 'unplanned': 'planning' not in row}[state]
    # Resolve eligibility on the full graph above; preference belongs to the
    # matching display projection, not to completed history hidden by filters.
    positions={(p,r['id']):n for n,(p,r) in enumerate(allrows)}
    queues={p:display_preferred([r for owner,r in allrows if owner==p],
                               [r for owner,r in allrows if owner==p and matches(owner,r)]) for p in namespaces}
    selected=[]
    while any(queues.values()):
        available=[(value(v[0])['deferred'],-value(v[0])['priority'],value(v[0])['order'],positions[(p,v[0]['id'])],p) for p,v in queues.items() if v]
        project=min(available)[-1];selected.append((project,queues[project].pop(0)))
    logical={key:query[key] for key in ('namespace','lifecycle','currentness','readiness','planning_filter','lifecycle_group') if query.get(key)}
    if selected_namespace:logical['namespace']=selected_namespace
    if query.get('q','').casefold().strip():logical['q']=query['q'].casefold().strip()
    cut=digest({'ordering':ORDERING_VERSION,'filters':logical,'namespaces':namespace_rows,
        'selected_order':[(p,r['id']) for p,r in selected],
        'rows':[(p,r['id'],r['work_revision'],r['work_status_revision'],projection(p,r),r['current_acceptance'],r['readiness']) for p,r in allrows]})
    if query.get('as_of') and query['as_of']!=cut:
        error=work.WorkConflict('Backlog observation, display order or logical filter changed between pages.','','',expected=query['as_of'],observed=cut)
        error.details['next_reads']=[catalogue_handle({**{k:v for k,v in query.items() if k not in {'as_of','offset','view'}},**({'namespace':caller_project} if mode!='human' else {})})]
        raise error
    fields = [{'name': 'q', 'label': 'Find in full Work ID, title and purpose', 'type': 'text', 'maxLength': 300}]
    for name, choices in [('namespace', permitted), ('lifecycle', sorted({r.get('recorded_status', 'open') for _, r in allrows})),
                          ('currentness', sorted({r['current_acceptance']['status'] for _, r in allrows})), ('readiness', sorted({r['readiness']['status'] for _, r in allrows})),
                          ('planning_filter', ['deferred', 'not-deferred', 'planned', 'unplanned']),('lifecycle_group',['unfinished'])]:
        fields.append({'name': name, 'label': name.replace('_', ' ').capitalize(), 'type': 'select', 'choices': [{'value': '', 'label': 'All'}, *[{'value': x, 'label': x} for x in choices]]})
    offset = query.get('offset', 0); limit = query.get('limit', 10); clean = {k: v for k, v in query.items() if k != 'view'}
    scope_query={'namespace':caller_project} if mode!='human' else {}
    clean.update(scope_query)
    envelope = {'schema_version': CATALOGUE, 'scope_id': 'work-backlog:' + (digest(str(root))[7:31] if mode=='human' else digest({'root':str(root),'namespace':caller_project})[7:31]), 'scope': ('Selected namespace Work observations within the admitted caller scope.' if selected_namespace else 'All existing Work namespaces in this owned workspace, including unregistered namespaces.'),
        'read_only': True, 'query': clean, 'read_cut': {'revision': cut, 'meaning': 'Observed per-owner Work and evidence cuts, not an atomic filesystem snapshot.'},
        'read': catalogue_handle(clean), 'query_action': {'read': catalogue_handle(scope_query), 'fields': fields, 'allowed_inputs': [f['name'] for f in fields]},
        'namespaces': namespace_rows, 'coverage': {'total_work': len(allrows), 'matching_work': len(selected), 'namespaces': len(namespaces), 'registered_work': sum(1 for p, _ in allrows if p in registered)},
        'active_read': catalogue_handle({'lifecycle_group':'unfinished','planning_filter':'not-deferred',**scope_query}), 'all_read':catalogue_handle(scope_query),
        'ordering': {'version':ORDERING_VERSION,'kind':'Necessary visible prerequisites first, then not deferred, higher priority, lower preferred order, stable legacy position',
            'hidden_prerequisites':'Traverse hidden unmet nodes; stop only at the Work owner prerequisite-satisfaction result. Full readiness, missing/cycle diagnosis and action guards are unchanged.', 'authority': 'Planning preference and readiness are not execution permission. Missing/cyclic prerequisites remain explicit.'}, 'rows': []}
    if mode=='human':
        from laplace.work.source_kernel import handle
        source_entry={'facet':'source-kernel','view':'contracts'}
        # The explicit catalogue filter narrows this human read only. A raw Work
        # namespace is not itself a registered project/body-reading capability.
        if selected_namespace in permitted and selected_namespace in registered:
            from laplace.pipeline import registry
            try:
                registered_project=registry.resolve(selected_namespace,repo_root=root)
            except (OSError,ValueError):
                registered_project=None
            if registered_project is not None and owner_discovery.owned_workspace('http').admits(selected_namespace):
                source_entry['namespace']=selected_namespace
        envelope['source_inspector_read']=handle(source_entry)
        envelope['historical_obligations_reads']=[{'title':title,'read':handle({'facet':'historical-obligations','source':source,'state':'open'})}
            for source,title in [('work_orders','Historical engine work orders'),('promises','Historical engine promises')]]
    candidate=next(((p,r) for p,r in selected if r.get('status')=='ready' and not value(r)['deferred'] and r.get('recorded_status') not in {'done','verified','cancelled','withdrawn'}),None)
    envelope['suggested_next']=({'state':'SUGGESTED','namespace':candidate[0],'id':candidate[1]['id'],'qualified_id':candidate[0]+'::'+candidate[1]['id'],'title':candidate[1].get('title','')[:512],'readiness':'READY','detail_read':views.handle(candidate[0],{'view':'detail','id':candidate[1]['id']})} if candidate else {'state':'NONE','reason':'No matching dependency-ready nondeferred Work is suggested.'})
    envelope['suggested_next']['qualification']='Planning recommendation only; inspect current evidence, actual activity and authority before any explicit execution.'
    def finish(covered):
        nxt = offset + covered if offset + covered < len(selected) else None
        envelope['pagination'] = {'total': len(selected), 'offset': offset, 'limit': limit, 'covered': covered, 'returned': len(envelope['rows']), 'next_offset': nxt,
            'next_read': catalogue_handle({**clean, 'offset': nxt, 'limit': limit, 'as_of': cut}) if nxt is not None else None,
            'bounded_by': 'bytes' if covered < min(limit, max(0, len(selected) - offset)) else 'limit'}
        return envelope
    covered = 0
    for project, row in selected[offset:offset + limit]:
        public=views._public(row,project)
        item = {k: copy.deepcopy(public[k]) for k in ('id', 'title', 'parent_work_id', 'depends_on', 'status', 'recorded_status', 'lifecycle', 'current_acceptance', 'readiness', 'currentness') if k in public}
        item.update(namespace=project, qualified_id=project + '::' + row['id'], registered=project in registered,
                    reference={k:v for k,v in owner_discovery.work_reference(project,row['id'],revision=row['work_revision']).items() if k!='legacy'}, planning=projection(project, row),
                    owner='domain.work', activity={'state':'NOT_OBSERVED','qualification':'This catalogue did not inspect execution; exact Work detail observes activity.'},
                    next_instruction='Inspect this Work for its exact prerequisites, current evidence and permitted next actions; planning does not start execution.',
                    detail_read=views.handle(project, {'view': 'detail', 'id': row['id']}), summary_read=views.handle(project, {'view': 'roots'}),
                    hierarchy_read=views.handle(project, {'view': 'branch', 'id': row['id']}), planning_read=planning_read(project,row['id']),
                    review_evidence_read=__import__('laplace.work.review_evidence',fromlist=['handle']).handle(project,row['id']),
                    provenance_read=__import__('laplace.work.project_work_evidence',fromlist=['handle']).handle(project,row['id']))
        item['title'] = row.get('title', '')[:512]; item['title_complete'] = item['title'] == row.get('title', '')
        item['purpose'] = row.get('goal', '')[:256]; item['purpose_complete'] = item['purpose'] == row.get('goal', '')
        if project in registered:item['human_destination']={'title':'Open Work in project','http':{'method':'GET','url':'/project?'+urlencode({'workspace':'writing','corpus':project,'view':'work','work':row['id']})},'meaning':'Navigation only; preserves existing project and Work authority.'}
        envelope['rows'].append(item); finish(covered + 1)
        if len(json.dumps(envelope, ensure_ascii=False).encode()) > CAP:
            envelope['rows'].pop()
            if covered: break
            envelope['rows'].append({'namespace': project, 'id': row['id'], 'qualified_id': project + '::' + row['id'], 'oversized': True,
                                     'detail_read': views.handle(project, {'view': 'detail', 'id': row['id']})})
        covered += 1
    finish(covered)
    if len(json.dumps(envelope, ensure_ascii=False).encode()) > CAP:
        raise ValueError('Backlog page metadata exceeds its bounded output; use an exact namespace.')
    return envelope
