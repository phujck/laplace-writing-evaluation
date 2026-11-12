"""Engineering assurance over canonical concept bindings and scoped work evidence.

No stored status or dispatcher: the concept retains a consumed acceptance, work
retains its evidence, and every read compares those exact bases. Historical
passage support remains a separate observation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlencode

FIELD = 'engineering_support'
VALIDATION_SCHEMA = 'laplace.engineering-validation/1'
_BINDING_KEYS = {'work_id', 'completion_revision', 'meaning_revision', 'covered_scope', 'validation_path'}
_HASH = re.compile(r'^(?:sha256:)?[0-9a-f]{64}$')
MAX_BINDINGS = 8
MAX_RECEIPT_BYTES = 65536


def _hash(value):
    return str(value).removeprefix('sha256:')


def _path(root, value):
    if not isinstance(value, str) or not value:
        raise ValueError('Engineering evidence needs an exact repository-relative path')
    raw = Path(value)
    path = (root / raw).resolve()
    if raw.is_absolute() or '..' in raw.parts or not path.is_relative_to(root):
        raise ValueError('Engineering evidence must stay inside the active checkout')
    return path


def binding_schema():
    string = {'type': 'string', 'minLength': 1}
    return {'type': 'array', 'maxItems': MAX_BINDINGS, 'items': {
        'type': 'object', 'additionalProperties': False,
        'required': sorted(_BINDING_KEYS), 'properties': {
            'work_id': string, 'validation_path': {**string,'description':'Pinned laplace.engineering-validation/1 receipt with distinct explicit source/test input roles, result identity and named observations; roleless earlier receipts remain review-required.'},
            'covered_scope': {**string, 'maxLength': 1000},
            'completion_revision': {'type': 'string', 'pattern': _HASH.pattern},
            'meaning_revision': {'type': 'string', 'pattern': _HASH.pattern}}}}


def _bindings(value):
    from jsonschema import Draft202012Validator
    error = next(Draft202012Validator(binding_schema()).iter_errors(value), None)
    if error:
        raise ValueError('engineering_support: ' + error.message)
    keys = [(row['work_id'], row['covered_scope']) for row in value]
    if len(keys) != len(set(keys)):
        raise ValueError('Engineering support repeats a work/scope binding')
    return value


def validation_schema():
    """The authored receipt shape, shared with help and fixture producers."""
    pin={'type':'object','additionalProperties':False,'required':['path','sha256'],
         'properties':{'path':{'type':'string','minLength':1},'sha256':{'type':'string','pattern':_HASH.pattern}}}
    return {'type':'object','additionalProperties':False,
            'required':['schema_version','claim_id','meaning_revision','covered_scope','inputs','outcome','checks','result_evidence'],
            'properties':{'schema_version':{'const':VALIDATION_SCHEMA},'claim_id':{'type':'string','minLength':1},
            'meaning_revision':{'type':'string','pattern':_HASH.pattern},'covered_scope':{'type':'string','minLength':1,'maxLength':1000},
            'outcome':{'const':'PASS'},'result_evidence':pin,
            'inputs':{'type':'array','minItems':2,'maxItems':64,'items':{**pin,'required':['path','sha256','role'],
                'properties':{**pin['properties'],'role':{'enum':['source','test']}}},
                'allOf':[{'contains':{'properties':{'role':{'const':role}},'required':['role']}} for role in ['source','test']]},
            'checks':{'type':'array','minItems':1,'maxItems':64,'items':{'type':'object','additionalProperties':False,
                'required':['name','passed'],'properties':{'name':{'type':'string','minLength':1,'maxLength':200},'passed':{'const':True}}}}}}


def _producer_consumers(root, task, context):
    """Reject only evidence consumed by this completion and its prerequisites.

    Containing goals control scope but their descriptive attachments are not
    consumed completion evidence. All paths come from their canonical owners.
    """
    from laplace.work import project_work
    from laplace.research import corpus_ingest
    from laplace.manuscript import project_protocol
    key=('engineering-producer-consumers',str(root),task['project'],task['id'])
    if context.get(key):return
    tasks=context[('core-work',str(root),task['project'])]['tasks']
    pending=[task['id']];seen=set();evidence=[];forbidden={project_work._ledger(root).resolve()}
    while pending:
        ident=pending.pop()
        if ident in seen:continue
        seen.add(ident);row=tasks.get(ident)
        if row is None:raise ValueError('Consumed prerequisite is unavailable')
        pending.extend(row.get('depends_on') or [])
        forbidden.add(corpus_ingest._rewire_path(root,row['project']).resolve())
        forbidden.update((root/path).resolve() for path in project_protocol.guide_paths(row['project'],root))
        evidence.extend(row.get('evidence_receipts') or [])
    for pin in evidence:
        if _path(root,pin['path']) in forbidden:
            raise ValueError('Producer completion consumes a mutable acknowledgement guide/work/concept ledger: '+pin['path'])
    context[key]=True


def _validation(root, path, task, node_id, meaning, scope, node, context):
    """Check a small retained result and its complete declared code/test basis."""
    _producer_consumers(root,task,context)
    pins = {row['path']: _hash(row['sha256']) for row in task.get('evidence_receipts') or []}
    target = _path(root, path)
    if path not in pins:
        raise ValueError('Validation receipt is not pinned by this work completion')
    key = ('engineering-validation', str(target), pins[path])
    if key not in context:
        if not target.is_file() or target.stat().st_size > MAX_RECEIPT_BYTES:
            raise ValueError('Validation receipt is missing or exceeds 64 KB')
        work_cache=context[('core-work',str(root),task['project'])]['digests']
        raw=work_cache.get(('evidence-body',target))
        if raw is None:
            # A caller may have observed work before requesting its tiny receipt.
            # Materialize/verify once and retain it only inside this request.
            raw=target.read_bytes()
            import hashlib
            if hashlib.sha256(raw).hexdigest()!=pins[path]:
                raise ValueError('Validation receipt changed during the support read')
            work_cache[('evidence-body',target)]=raw
            io=work_cache.setdefault(('evidence-materialization-io',),{'visits':0,'bytes':0})
            io['visits']+=1;io['bytes']+=len(raw)
        context[key] = json.loads(raw)
    value = context[key]
    from jsonschema import Draft202012Validator
    error=next(Draft202012Validator(validation_schema()).iter_errors(value),None)
    if error:raise ValueError('Validation schema mismatch at '+str(list(error.absolute_path))+': '+error.validator+'; explicit source/test roles and exact evidence are required')
    if value.get('claim_id') != node_id or value.get('meaning_revision') != meaning:
        raise ValueError('Validation does not cover the current claim meaning; revalidate it')
    if value['covered_scope'] != scope:
        raise ValueError('Validation does not establish this exact covered scope')
    checks=value['checks'];inputs=value['inputs'];result=value['result_evidence']
    resolved=[_path(root,row['path']) for row in inputs]
    if len(set(resolved))!=len(resolved):raise ValueError('Validation repeats a resolved source/test pin')
    for pin in [*inputs, result]:
        _path(root, pin['path'])
        if _path(root,pin['path'])==target:
            raise ValueError('Validation cannot consume its own receipt as input/result')
        if pins.get(pin['path']) != _hash(pin['sha256']):
            raise ValueError('Validation input/result is missing or differs from the completion evidence: ' + pin['path'])
    refs = node.get('source') or node.get('sources') or node.get('ref') or []
    refs = refs if isinstance(refs, list) else [refs]
    input_pins = {pin['path']: _hash(pin['sha256']) for pin in inputs if pin['role']=='source'}
    covered = [ref for ref in refs if isinstance(ref, dict) and ref.get('path') in input_pins]
    if not covered:
        raise ValueError('Validation must cover an exact live source locator of this claim')
    for ref in covered:
        if ref.get('repository'):
            from laplace.projects import writing_sources
            _repository, resolved_source = writing_sources._path(root, ref)
            if resolved_source.resolve() != _path(root, ref['path']):
                raise ValueError('Covered source belongs to another repository edition')
        if not isinstance(ref.get('sha256'), str) or _hash(ref['sha256']) != input_pins[ref['path']]:
            raise ValueError('Covered claim source pin differs from validation: ' + ref['path'])
        # Work observed the same repository file; do not read/hash its body again.
        _path(root, ref['path'])
    return {'covered_sources': [ref['path'] for ref in covered], 'checks': len(checks)}


def observe(project, node_id, root, net, *, read_context=None, declarations=None):
    from laplace.work import project_work
    from laplace.research import literature_support
    from laplace.work.project_work_views import handle
    root = Path(root).resolve(); context = {} if read_context is None else read_context
    node = (net.get('nodes') or {}).get(node_id) or {}
    value = (node.get('projection') or {}).get(FIELD, []) if declarations is None else declarations
    try:
        bindings = _bindings(value)
    except ValueError as exc:
        return {'status': 'REVIEW_REQUIRED', 'bindings': [], 'reason': str(exc), 'read_metrics': {}}
    if not bindings:
        return {'status': 'UNDECLARED', 'bindings': [], 'reason': 'No engineering support has been adopted', 'read_metrics': {}}
    meaning = literature_support.meaning_revision(project, node_id, root, net,read_context=context)
    observed = project_work.observe_core(project, [row['work_id'] for row in bindings], root, read_context=context, materialize_paths=[row['validation_path'] for row in bindings])
    rows = []
    for binding in bindings:
        task = observed['tasks'].get(binding['work_id'])
        row = {**binding, 'current_meaning_revision': meaning,
               'read_handle': handle(project, {'view': 'detail', 'id': binding['work_id']}),
               'qualification': 'SCOPED_ENGINEERING_OBSERVATION', 'independent_verification': 'NOT_ASSERTED'}
        state = 'CURRENT'; reason = 'The exact adopted work, meaning and validation inputs remain current'
        producer_issue=None
        if task:
            try:_producer_consumers(root,task,context)
            except (OSError,ValueError,KeyError,TypeError) as exc:producer_issue=str(exc)
        if producer_issue:
            state, reason = 'REVIEW_REQUIRED', producer_issue
        elif not task:
            state, reason = 'REVIEW_REQUIRED', 'Engineering support work is unavailable'
        elif not task.get('completion_work_basis'):
            state, reason = 'REVIEW_REQUIRED', 'Engineering work has no exact consumed scope basis'
        elif task.get('task_kind') != 'engineering':
            state, reason = 'REVIEW_REQUIRED', 'Support must name scoped engineering work'
        elif task.get('status') != 'done' or (task.get('currentness') or {}).get('status') != 'CURRENT':
            state, reason = 'STALE', (task.get('currentness') or {}).get('reason') or 'Engineering work or its prerequisites are not current'
        else:
            try:
                row.update(_validation(root, binding['validation_path'], task, node_id, meaning, binding['covered_scope'], node, context))
                if binding['completion_revision'] != task['completion_revision'] or binding['meaning_revision'] != meaning:
                    state, reason = 'ACK_REQUIRED', 'The revalidated work or meaning requires explicit adoption of its exact basis'
            except (OSError, ValueError, KeyError, TypeError) as exc:
                state, reason = 'REVIEW_REQUIRED', str(exc)
        row.update(status=state, reason=reason,
                   current_completion_revision=task.get('completion_revision') if task else None,
                   work_currentness=task.get('currentness') if task else None)
        if task:
            # This is only a proposal for the existing guarded writer, never auto-adoption.
            row['adoption_permitted'] = state in {'CURRENT', 'ACK_REQUIRED'}
            row['adoption'] = {'work_id': binding['work_id'], 'completion_revision': task['completion_revision'],
                'meaning_revision': meaning, 'covered_scope': binding['covered_scope'], 'validation_path': binding['validation_path']}
        rows.append(row)
    status = 'CURRENT' if all(row['status'] == 'CURRENT' for row in rows) else 'REVIEW_REQUIRED'
    io=context[('core-work',str(root),project)]['digests'].get(('evidence-materialization-io',),{})
    observed['read_metrics'].update(receipt_materialization_visits=io.get('visits',0),receipt_materialization_bytes=io.get('bytes',0))
    return {'status': status, 'bindings': rows, 'meaning_revision': meaning,
            'reason': 'All covered engineering observations are current' if status == 'CURRENT' else 'Inspect and explicitly renew the affected engineering support',
            'read_metrics': observed['read_metrics']}


def validate_adoption(project, node_id, root, net, declarations):
    _bindings(declarations)
    result = observe(project, node_id, root, net, declarations=declarations)
    if result['status'] not in {'CURRENT', 'UNDECLARED'}:
        raise ValueError('Engineering adoption refused: ' + '; '.join(row['reason'] for row in result['bindings']))
    return declarations


def guide_nodes(content, project):
    """Existing Markdown concept links are the guide's references, not a registry."""
    nodes = []
    for url in re.findall(r'\]\(([^)]+)\)', content):
        parsed = urlsplit(url); query = parse_qs(parsed.query)
        if parsed.path not in {'/concepts/state', '/project'}:
            continue
        if query.get('project', query.get('corpus', [project]))[0] != project:
            continue
        node = query.get('node', [''])[0]
        if node and node not in nodes:
            nodes.append(node)
    return nodes


def guide_support(project, node_ids, root, *, read_context=None):
    from laplace.research import literature_support
    context = {} if read_context is None else read_context
    key = ('engineering-network', str(root), project)
    if key not in context:
        context[key] = literature_support.network(project, root)
    net = context[key]
    node_ids = [ident for ident in node_ids if FIELD in ((net.get('nodes') or {}).get(ident, {}).get('projection') or {})]
    omitted=max(0,len(node_ids)-MAX_BINDINGS);node_ids=node_ids[:MAX_BINDINGS]
    rows = [{'node': ident, **observe(project, ident, root, net, read_context=context),
             'read_handle': {'operation': 'concept', 'payload': {'node': ident},
                             'http': {'method': 'GET', 'url': '/concepts/state?' + urlencode({'project':project,'node':ident})}}}
            for ident in node_ids]
    return {'status': 'REVIEW_REQUIRED' if omitted else 'UNDECLARED' if not rows else 'CURRENT' if all(row['status'] == 'CURRENT' for row in rows) else 'REVIEW_REQUIRED',
            'coverage': {'returned_claims':len(rows),'omitted_claims':omitted},
            'claims': rows, 'reason': 'Engineering support exceeds the bounded guide view; inspect omitted claims before trust' if omitted else 'Read the linked engineering basis before relying on this guide'}
