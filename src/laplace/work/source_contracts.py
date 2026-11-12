"""SOURCE CONTRACTS (source-as-a-state slice, WORK-source-contract-reflexive-slice-20261021): an operation's owner states its
contract as named SEGMENTS of declared facts, and its explicit consumers as TYPED RELATIONS to the segments they rest on.
This module is the generic part: it holds no operation, field or path of its own.

Declaration (laplace.source-contract/1), returned by the owning module's ``source_contract()``:
  owner, operation, purpose (authored text and assumptions, attributable, never inferred from source)
  segments   {id: facts}: each segment's facts are computed by the owner from the declarations its code runs (its
             schema, request rule, composition steps, human inputs); a segment's BASIS is the canonical digest of its
             facts (core.identity), not of a file, an import graph or a path
  relations  [{consumer, relation, segments, location?, says?}]: relation is one of RELATIONS; ``location`` only
             qualifies where the consumer's implementation lives - it is not evidence of what it consumes
  steps      the constituent steps (for descent), each {id, primitive, object, effect, guard?}; the declaration
             CONTAINS them
Roles (core.scoped): a consumer's accepted segment bases are CONSUMED meaning. A changed consumed segment makes that
consumer locally PENDING_REVIEW (its earlier acceptance is not renewed by the change); an unchanged segment keeps it
CURRENT; a consumer whose accepted basis is unknown is UNREVIEWED, never assumed current. Raw source-byte CAS (the
development_source owner's before_sha256) guards file effects and is separate from these semantic bases.
Custody and acceptance (SC-R1, canonical): an existing Work review obligation may carry an optional typed binding
(``binding``: owner, operation, consumer, segments?). The existing handoff that covers it PUBLISHES the owning
declaration's selected segments (``publish``): each segment's exact canonical body goes through the real Writing body
store (representation.writing_bodies, core.bodies) and the identity, declaration version, all segment bases and the
selected body references are embedded in that handoff phase row - the canonical version receipt. The existing review
of that obligation copies exactly the handed consumer and bases. ``record`` folds those durable phase rows (the latest
disposition per consumer; only an ACCEPT whose recorded independence is INDEPENDENT is acceptance; a later HOLD or
REJECT is never covered by an older ACCEPT; SELF/UNKNOWN stays unreviewed) and ``canonical_standing`` judges the
current declaration against them. ``read_version`` returns a retained version's exact bodies; an unknown version is
refused, never substituted. ``standing`` with a supplied map remains the generic rule those reads apply. Recording a
receipt or a review never changes a segment basis, so an observation cannot recursively stale itself. Identity is
owner + operation (``reference``); the Work and project qualify custody, admission and review responsibility only.
Public reads are detached JSON snapshots (``detached``): changing a returned value never changes a live declaration.
Descent: ``inspect`` gives the coarse contract (purpose, segment bases, relation counts, steps by id) and, with
``select='step:<id>'`` or ``'segment:<id>'``, exactly one constituent with the owner's authority and recovery kept,
under a byte budget that refuses rather than truncates silently.
"""
from __future__ import annotations

import json
import re

from laplace.core import bodies, scoped
from laplace.core.identity import canonical_bytes, canonical_digest, reference as owner_reference

SCHEMA = 'laplace.source-contract/1'
RELATIONS = ('implements', 'consumes', 'projects', 'evaluates', 'explains', 'contains')
STANDINGS = ('CURRENT', 'PENDING_REVIEW', 'UNREVIEWED', 'HELD', 'REJECTED')
KIND = 'source-contract'
BINDING_KEYS = ('owner', 'operation', 'consumer', 'segments')
DEFAULT_BUDGET = 16 * 1024


def detached(value):
    """A JSON snapshot that shares nothing with live owner state (canonical JSON round trip)."""
    return json.loads(canonical_bytes(value))


def validate(declaration: dict) -> dict:
    """The declaration's own shape: every relation names known segments and a known relation kind."""
    if declaration.get('schema') != SCHEMA:
        raise ValueError('A source contract declares schema ' + SCHEMA + '.')
    for key in ('owner', 'operation', 'purpose', 'segments', 'relations'):
        if not declaration.get(key):
            raise ValueError('A source contract declares ' + key + '.')
    for row in declaration['relations']:
        if row.get('relation') not in RELATIONS:
            raise ValueError('Unknown relation ' + repr(row.get('relation')) + '; relations are ' + ', '.join(RELATIONS) + '.')
        unknown = [name for name in row.get('segments') or () if name not in declaration['segments']]
        if not row.get('consumer') or not row.get('segments') or unknown:
            raise ValueError('Relation of ' + repr(row.get('consumer')) + ' names unknown segments ' + repr(unknown) + '.')
    return declaration


def key(declaration: dict) -> str:
    return declaration['owner'] + ':' + declaration['operation']


def bases(declaration: dict) -> dict:
    """Each segment's basis: the canonical digest of its declared facts."""
    return {name: canonical_digest(facts) for name, facts in validate(declaration)['segments'].items()}


def accepted_bases(declaration: dict, consumer: str) -> dict:
    """What a reviewer accepting ``consumer`` now records: exactly the segments that consumer's relations rest on."""
    current = bases(declaration)
    names = sorted({name for row in declaration['relations'] if row['consumer'] == consumer for name in row['segments']})
    if not names:
        raise ValueError('No relation of ' + key(declaration) + ' names consumer ' + repr(consumer) + '.')
    return {name: current[name] for name in names}


def standing(declaration: dict, accepted: dict) -> dict:
    """Every consumer's standing against its accepted segment bases (``accepted``: {consumer: {segment: basis}}), with
    one typed local obligation per changed consumed segment. Only the consumers of a changed segment become pending."""
    current = bases(declaration)
    consumers = {}
    for row in declaration['relations']:
        consumers.setdefault(row['consumer'], {'relations': set(), 'segments': set()})
        consumers[row['consumer']]['relations'].add(row['relation'])
        consumers[row['consumer']]['segments'].update(row['segments'])
    out, obligations = {}, []
    for consumer, held in sorted(consumers.items()):
        recorded = accepted.get(consumer)
        if not recorded:
            out[consumer] = {'standing': 'UNREVIEWED', 'relations': sorted(held['relations']), 'segments': sorted(held['segments'])}
            continue
        observed = [scoped.observation(key(declaration) + '#' + name, 'consumed', expected=recorded.get(name), observed=current[name])
                    for name in sorted(held['segments'])]
        changed = [row for row in observed if row['state'] != 'CURRENT']
        local = [scoped.obligation('SOURCE_CONTRACT_SEGMENT_CHANGED',
                                   'The ' + row['subject'] + ' segment ' + consumer + ' rests on changed since it was accepted; review it.',
                                   subject={'consumer': consumer, 'segment': row['subject']}, basis=row['expected'], key=row['observed'])
                 for row in changed]
        obligations.extend(local)
        out[consumer] = {'standing': 'PENDING_REVIEW' if changed else 'CURRENT', 'relations': sorted(held['relations']),
                         'segments': sorted(held['segments']), 'changed': [row['subject'].rsplit('#', 1)[1] for row in changed],
                         **({'obligations': [row['id'] for row in local]} if local else {})}
    changed_segments = sorted({name for row in out.values() for name in row.get('changed') or ()})
    return {'schema': SCHEMA, 'operation': key(declaration), 'bases': current, 'consumers': out, 'changed_segments': changed_segments,
            'obligations': scoped.merge(obligations), 'semantic_currentness': scoped.semantic_currentness(obligations)}


def retain(declaration: dict, put, store: str) -> dict:
    """Put each segment's exact canonical body through the owner's store; returns {segment: body reference}."""
    out, diagnostic = {}, bodies.degradation()
    for name, facts in validate(declaration)['segments'].items():
        reference = bodies.retain(put, store, canonical_bytes(facts), diagnostic)
        if reference is None:
            raise OSError('The ' + name + ' segment body could not be retained.')
        out[name] = reference
    return out


def inspect(declaration: dict, select: str | None = None, *, budget: int = DEFAULT_BUDGET) -> dict:
    """Coarse contract, or one selected constituent (``step:<id>`` / ``segment:<id>``) with the owner's authority kept."""
    current = bases(declaration)
    steps = declaration.get('steps') or []
    handle = lambda what: {'select': what}
    if select is None:
        value = {'schema': SCHEMA, 'operation': key(declaration), 'purpose': declaration['purpose'],
                 'segments': [{'id': name, 'basis': basis, 'next': handle('segment:' + name)} for name, basis in current.items()],
                 'relations': {kind: sum(1 for row in declaration['relations'] if row['relation'] == kind) for kind in RELATIONS},
                 'steps': [{'id': row['id'], 'object': row.get('object'), 'next': handle('step:' + row['id'])} for row in steps],
                 'authority': declaration.get('authority'), 'recovery': declaration.get('recovery')}
    else:
        kind, _, ident = select.partition(':')
        if kind == 'step':
            found = next((row for row in steps if row['id'] == ident), None)
        elif kind == 'segment':
            found = {'id': ident, 'basis': current[ident], 'facts': declaration['segments'][ident],
                     'consumers': [row for row in declaration['relations'] if ident in row['segments']]} if ident in current else None
        else:
            found = None
        if found is None:
            raise ValueError('No ' + select + ' in ' + key(declaration) + '; select step:<id> or segment:<id> from its coarse contract.')
        value = {'schema': SCHEMA, 'operation': key(declaration), 'selected': select, 'item': found,
                 'up': handle(None), 'authority': declaration.get('authority'), 'recovery': declaration.get('recovery'),
                 'bases': {'contract': canonical_digest(current)}}
    size = len(json.dumps(value, sort_keys=True, default=str).encode())
    if size > budget:
        raise bodies.BudgetExceeded('The ' + (select or 'coarse') + ' contract read is ' + str(size) + ' bytes; budget ' + str(budget) + '.')
    return detached(value)


def listing(*, budget=None) -> dict:
    """Every declared operation's identity, current version and segment ids, as one envelope within the budget."""
    budget = DEFAULT_BUDGET if budget is None else budget
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= MAX_BUDGET:
        raise Refusal('MALFORMED_BUDGET', 'budget is an integer number of bytes from 1 to %d.' % MAX_BUDGET)
    return _fit({'schema': SCHEMA, 'operations': [{'reference': reference(row['owner'], row['operation'], version(row)),
                                                   'purpose': row['purpose']['text'], 'segments': sorted(row['segments']),
                                                   'steps': [step['id'] for step in row.get('steps') or []]} for row in declarations()]},
                budget, 'operation list')


def providers() -> tuple:
    """The existing declaration registry, also usable to qualify declaring-source custody."""
    from laplace.work import development_source, project_work_review
    from laplace.representation import source_publication
    from laplace.engine import session_memory
    from laplace.writing import session_projection
    return (project_work_review.source_contract, development_source.source_contract, source_publication.source_contract,
            session_memory.source_contract, session_projection.source_contract)


def declarations() -> list:
    """The registered owners' declared operation contracts, each from its owning module."""
    return [provider() for provider in providers()]


# ---------------------------------------------------------------------------------------------- canonical custody and review

def declaration(owner: str, operation: str) -> dict:
    """The current declaration of a registered operation (from its owning module); an unknown identity is refused."""
    for row in declarations():
        if row['owner'] == owner and row['operation'] == operation:
            return row
    raise Refusal('UNSUPPORTED_OPERATION', 'no declared source contract %s:%s.' % (owner, operation))


def reference(owner: str, operation: str, version: str | None = None) -> dict:
    """The neutral owner reference of one source contract: identity is the operation under its owner, never a project."""
    return owner_reference(owner, KIND, {'operation': operation}, version={'declaration': version} if version else None)


def version(declaration_: dict) -> str:
    """A declaration's version: the digest of all its segment bases."""
    return canonical_digest(bases(declaration_))


def binding(value) -> dict:
    """The SHAPE of an authored obligation binding {owner, operation, consumer, segments?}; resolution is at publication."""
    if not isinstance(value, dict) or set(value) - set(BINDING_KEYS) or any(not isinstance(value.get(key), str) or not value[key].strip()
                                                                          for key in ('owner', 'operation', 'consumer')):
        raise ValueError('A source_contract binding has owner, operation and consumer text and optional segments.')
    out = {key: value[key] for key in ('owner', 'operation', 'consumer')}
    if 'segments' in value:
        segments = value['segments']
        if not isinstance(segments, list) or not segments or len(segments) > 16 or len(set(segments)) != len(segments) \
                or any(not isinstance(name, str) or not name for name in segments):
            raise ValueError('source_contract segments are distinct segment ids (1-16).')
        out['segments'] = list(segments)
    return out


def consumed_segments(declaration_: dict, consumer: str) -> list:
    """Every segment the consumer's declared relations rest on: the coverage a whole-consumer review needs."""
    return sorted({name for row in declaration_['relations'] if row['consumer'] == consumer for name in row['segments']})


def publish(root, binding_: dict) -> dict:
    """Resolve a binding against the registered owner and retain its selected segments through the Writing body store.
    Unsupported identity, an unknown consumer or a segment that consumer does not consume refuses the publication."""
    from laplace.representation import writing_bodies
    current = declaration(binding_['owner'], binding_['operation'])
    consumed = consumed_segments(current, binding_['consumer'])
    if not consumed:
        raise Refusal('UNKNOWN_CONSUMER', '%s declares no consumer %s.' % (key(current), binding_['consumer']))
    selected = binding_.get('segments') or consumed
    extra = sorted(set(selected) - set(consumed))
    if extra:
        raise Refusal('SEGMENT_NOT_CONSUMED', '%s does not consume %s of %s.' % (binding_['consumer'], ', '.join(extra), key(current)))
    all_bases, diagnostic, held = bases(current), bodies.degradation(), {}
    for name in sorted(selected):
        ref = bodies.retain(lambda raw: writing_bodies.store(root).put(raw), writing_bodies.STORE,
                            canonical_bytes(current['segments'][name]), diagnostic)
        if ref is None:
            raise OSError('The %s segment body of %s could not be retained; nothing was handed off.' % (name, key(current)))
        held[name] = {'basis': all_bases[name], 'body': ref}
    result = {'schema': SCHEMA, 'owner': current['owner'], 'operation': current['operation'], 'consumer': binding_['consumer'],
            'version': canonical_digest(all_bases), 'bases': all_bases, 'segments': held}
    if binding_['consumer'] == 'kernel.declared-source':
        context = {key: current.get(key) for key in ('purpose','authority','recovery')}
        context['relations'] = [row for row in current['relations'] if set(row['segments']) & set(selected)]
        import sys, hashlib
        from pathlib import Path
        provider=next(fn for fn in providers() if fn()['owner']==current['owner'] and fn()['operation']==current['operation'])
        path=Path(sys.modules[provider.__module__].__file__)
        if path.stat().st_size>1024*1024:raise Refusal('BUDGET_EXCEEDED','Declaring source exceeds the source input bound.')
        code=path.read_bytes()
        context['declaring_source']={'path':'src/'+provider.__module__.replace('.','/')+'.py','sha256':'sha256:'+hashlib.sha256(code).hexdigest(),'bytes':len(code)}
        raw = canonical_bytes(context)
        if len(raw) > MAX_BUDGET:raise Refusal('BUDGET_EXCEEDED','Selected kernel context exceeds the retained input bound.')
        ref = bodies.retain(lambda data: writing_bodies.store(root).put(data), writing_bodies.STORE, raw, diagnostic)
        if ref is None:raise OSError('Kernel context could not be retained; nothing was handed off.')
        result['kernel_context'] = {'basis': canonical_digest(context), 'body': ref}
    return result


class Refusal(ValueError):
    """A typed refusal of a source-contract publication or read: a code, the reason and nothing read past it."""
    def __init__(self, code: str, message: str, **facts):
        super().__init__(code + ': ' + message)
        self.details = {'code': code, **detached(facts)}


MAX_BUDGET = 64 * 1024
_VERSION = re.compile(r'sha256:[0-9a-f]{64}')
_SELECT = re.compile(r'(step|segment):[A-Za-z0-9._-]{1,64}')
#: the binding a source-scope review obligation may carry: the task door's schema is generated from this
BINDING_SCHEMA = {'type': 'object', 'required': ['owner', 'operation', 'consumer'], 'additionalProperties': False,
                  'properties': {'owner': {'type': 'string', 'minLength': 1}, 'operation': {'type': 'string', 'minLength': 1},
                                 'consumer': {'type': 'string', 'minLength': 1},
                                 'segments': {'type': 'array', 'minItems': 1, 'maxItems': 16, 'uniqueItems': True, 'items': {'type': 'string', 'minLength': 1}}}}


def binding_schema() -> dict:
    return detached(BINDING_SCHEMA)


def normalize(value, *, select=None, budget=None) -> dict:
    """THE one admission of a source-contract read, before any branch: an exact owner-qualified reference (kind
    source-contract, identity exactly {operation}, a declared operation of that owner), an optional version with
    exactly the key ``declaration`` (an explicit version always means that retained version), an optional selected
    constituent (step:<id> | segment:<id>) and the caller's byte budget for the WHOLE returned envelope."""
    from laplace.core.identity import reference_problems
    problems = reference_problems(value) if isinstance(value, dict) else ['not a reference object']
    if problems:
        raise Refusal('MALFORMED_REFERENCE', 'Not a reference: ' + '; '.join(problems))
    if value.get('kind') != KIND or set(value.get('identity') or {}) != {'operation'} or not isinstance(value['identity']['operation'], str):
        raise Refusal('MALFORMED_REFERENCE', 'A source-contract reference has kind source-contract and identity exactly {operation}.')
    owner, operation = value['owner'], value['identity']['operation']
    if not any(row['owner'] == owner and row['operation'] == operation for row in declarations()):
        known = [row['operation'] for row in declarations() if row['operation'] == operation]
        raise Refusal('WRONG_OWNER' if known else 'UNKNOWN_TARGET', 'No source contract %s is declared by %s.' % (operation, owner))
    requested = value.get('version')
    if requested is not None and (set(requested) != {'declaration'} or not isinstance(requested['declaration'], str)
                                  or not _VERSION.fullmatch(requested['declaration'])):
        raise Refusal('UNSUPPORTED_VERSION', 'A source-contract version is exactly {declaration: sha256:<64 hex>}.', requested=requested)
    if select is not None and (not isinstance(select, str) or not _SELECT.fullmatch(select)):
        raise Refusal('MALFORMED_SELECT', 'select is step:<id> or segment:<id>.', select=select)
    if budget is None:
        budget = DEFAULT_BUDGET
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= MAX_BUDGET:
        raise Refusal('MALFORMED_BUDGET', 'budget is an integer number of bytes from 1 to %d.' % MAX_BUDGET)
    return {'owner': owner, 'operation': operation, 'version': requested['declaration'] if requested else None,
            'select': select, 'budget': budget}


def _size(value) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode())


def _fit(envelope: dict, budget: int, what: str) -> dict:
    size = _size(envelope)
    if size > budget:
        raise Refusal('BUDGET_EXCEEDED', 'The %s read is %d bytes; the budget is %d. Select one step or segment, or raise the '
                      'budget up to %d.' % (what, size, budget, MAX_BUDGET), size=size, budget=budget)
    return detached(envelope)


def _pick(select, segments: dict, steps) -> dict:
    """The selected constituent with the same meaning over current and retained facts."""
    kind, _, ident = select.partition(':')
    if kind == 'segment':
        if ident not in segments:
            raise Refusal('UNKNOWN_SELECT', 'No segment %s in this version.' % ident)
        return {'id': ident, **segments[ident]}
    found = next((row for row in steps or () if isinstance(row, dict) and row.get('id') == ident), None)
    if found is None:
        raise Refusal('UNKNOWN_SELECT', 'No step %s in this version.' % ident)
    return found


def read(root, request: dict, *, admits=lambda namespace: True, read_scope=None) -> dict:
    """One normalized read (``normalize``): unversioned = the current declaration with canonical standing (readable
    even when unreviewed); an explicit version = exactly that retained version (refused if not retained, even when it
    equals the current digest). The whole envelope - standing and version history included - fits the budget, and a
    retained body's declared size is charged before it is read."""
    owner, operation, budget, select = request['owner'], request['operation'], request['budget'], request['select']
    current = declaration(owner, operation)
    if request['version'] is None:
        now = version(current)
        envelope = {'schema': SCHEMA, 'reference': reference(owner, operation, now), 'state': 'CURRENT_DECLARATION',
                    'standing': canonical_standing(root, owner, operation, admits=admits),
                    'source_kernel_read': __import__('laplace.work.source_kernel',fromlist=['handle']).handle({'facet':'source-kernel','reference':reference(owner,operation,now),**({'namespace':read_scope.namespace} if getattr(read_scope,'kind',None)=='project' else {})})}
        current_bases = bases(current)
        if select is None:
            envelope.update(purpose=current['purpose'], authority=current.get('authority'), recovery=current.get('recovery'),
                            segments=[{'id': name, 'basis': basis, 'next': {'select': 'segment:' + name}} for name, basis in current_bases.items()],
                            relations={kind: sum(1 for row in current['relations'] if row['relation'] == kind) for kind in RELATIONS},
                            steps=[{'id': row['id'], 'object': row.get('object'), 'next': {'select': 'step:' + row['id']}} for row in current.get('steps') or []])
        else:
            facts = {name: {'basis': basis, 'facts': current['segments'][name],
                            'consumers': [row for row in current['relations'] if name in row['segments']]} for name, basis in current_bases.items()}
            envelope.update(selected=select, item=_pick(select, facts, current.get('steps')), up={'select': None},
                            authority=current.get('authority'), recovery=current.get('recovery'))
        return _fit(envelope, budget, 'current ' + (select or 'coarse'))
    published = [row for row in record(root, owner, operation, admits=admits)['publications'] if row['version'] == request['version']]
    if not published:
        raise Refusal('UNKNOWN_VERSION', '%s:%s has no retained version %s in this scope; the current declaration is never '
                      'substituted for an explicit version.' % (owner, operation, request['version']))
    held = {}
    for row in published:
        held.update(row['segments'])
    envelope = {'schema': SCHEMA, 'reference': reference(owner, operation, request['version']), 'state': 'RETAINED_VERSION',
                'source_kernel_read': __import__('laplace.work.source_kernel',fromlist=['handle']).handle({'facet':'source-kernel','reference':reference(owner,operation,request['version']),**({'namespace':read_scope.namespace} if getattr(read_scope,'kind',None)=='project' else {})}),
                'bases': published[0]['bases'], 'not_retained': sorted(set(published[0]['bases']) - set(held)),
                'publications': [{key_: row[key_] for key_ in ('work', 'handoff_id', 'obligation_id', 'consumer', 'ts')} for row in published]}
    if select is None:
        envelope['retained'] = [{'id': name, 'basis': value['basis'], 'bytes': value['body'].get('size'),
                                 'next': {'select': 'segment:' + name}} for name, value in sorted(held.items())]
        return _fit(envelope, budget, 'retained coarse')
    kind, _, ident = select.partition(':')
    name = ident if kind == 'segment' else 'steps'
    if name not in held:
        raise Refusal('NOT_RETAINED', 'Version %s did not retain the %s segment that %s needs.' % (request['version'], name, select))
    body = held[name]['body']
    shell = {**envelope, 'selected': select}
    if _size(shell) + int(body.get('size') or 0) > budget:   # charged BEFORE the body is read
        raise Refusal('BUDGET_EXCEEDED', 'The retained %s read needs at least %d bytes; the budget is %d.' % (select, _size(shell) + int(body.get('size') or 0), budget),
                      size=_size(shell) + int(body.get('size') or 0), budget=budget)
    from laplace.representation import writing_bodies
    with bodies.budget(budget):
        facts = json.loads(writing_bodies.read_bytes(body, root))
    if canonical_digest(facts) != held[name]['basis']:
        raise Refusal('CORRUPT_BODY', 'The retained %s body does not match its recorded basis.' % name)
    segment = {name: {'basis': held[name]['basis'], 'facts': facts, 'verified': True}}
    item = _pick(select, segment, facts.get('steps') if isinstance(facts, dict) else None)
    return _fit({**shell, 'item': item, 'body_basis': held[name]['basis']}, budget, 'retained ' + select)


def record(root, owner: str, operation: str, *, admits=lambda namespace: True) -> dict:
    """The canonical publications and reviews of one source contract, folded from the Work ledger's phase rows."""
    publications, reviews = _fold(root, owner, operation, admits)
    return {'publications': list(publications.values()),
            'reviews': [{'review_id': row['id'], 'work': row['project'] + '::' + row['work_id'], 'handoff_id': row['handoff_id'],
                         'obligation_id': row['obligation_id'], 'consumer': row['source_contract']['consumer'],
                         'version': row['source_contract']['version'], 'segments': dict(row['source_contract']['segments']),
                         'verdict': row.get('verdict'), 'independence': row.get('independence'), 'ts': row.get('ts')} for row in reviews]}


def _fold(root, owner, operation, admits):
    from laplace.work import project_work
    publications, reviews = {}, []
    for row in project_work._rows(root):
        if row.get('record') != 'project-work-phase' or not admits(row.get('project')):
            continue
        if row.get('phase') == 'handoff':
            for obligation, entry in (row.get('source_contracts') or {}).items():
                if entry.get('owner') == owner and entry.get('operation') == operation:
                    publications[(row['project'], row['work_id'], row['id'], obligation)] = {
                        **entry, 'work': row['project'] + '::' + row['work_id'], 'handoff_id': row['id'], 'obligation_id': obligation,
                        'ts': row.get('ts')}
        elif row.get('phase') == 'review' and isinstance(row.get('source_contract'), dict):
            bound = row['source_contract']
            if bound.get('owner') == owner and bound.get('operation') == operation and \
                    (row['project'], row['work_id'], row.get('handoff_id'), row.get('obligation_id')) in publications:
                reviews.append(row)
    return publications, reviews


def canonical_standing(root, owner: str, operation: str, *, admits=lambda namespace: True) -> dict:
    """Each consumer's standing from its LATEST canonical review, judged by the review owner's one decision
    (project_work_review.decision: verdict, recorded independence, raw pins and handed segment bases now)."""
    from laplace.work import project_work, project_work_review
    current = declaration(owner, operation)
    _, reviews = _fold(root, owner, operation, admits)
    latest = {}
    for row in reviews:
        latest[row['source_contract']['consumer']] = row
    consumers, obligations, tasks_by = {}, [], {}
    for row in current['relations']:
        held = consumers.setdefault(row['consumer'], {'standing': 'UNREVIEWED', 'relations': set(), 'segments': set()})
        held['relations'].add(row['relation'])
        held['segments'].update(row['segments'])
    for consumer, row in latest.items():
        if consumer not in consumers:
            continue
        tasks = tasks_by.setdefault(row['project'], project_work._tasks(row['project'], root))
        task = tasks.get(row['work_id']) or {}
        obligation = next((item for item in task.get('review_obligations') or () if item['id'] == row['obligation_id']), None)
        entry = consumers[consumer]
        entry['review'] = {'review_id': row['id'], 'work': row['project'] + '::' + row['work_id'], 'version': row['source_contract']['version'],
                           'verdict': row.get('verdict'), 'independence': row.get('independence')}
        if obligation is None:
            entry.update(standing='UNREVIEWED', reason='The reviewed obligation is no longer declared on its Work.')
            continue
        judged = project_work_review.decision(row, obligation, root, intent=project_work_review.intent_digest(task, tasks))
        # the qualified facts of the one decision: local Work satisfaction, actual independence and actual coverage
        entry.update(reason=judged['reason'], independence=judged['independence'], local_satisfied=judged['satisfied'],
                     coverage=judged['coverage'])
        if judged['verdict'] in ('HOLD', 'REJECT'):
            entry['standing'] = 'HELD' if judged['verdict'] == 'HOLD' else 'REJECTED'
        elif not judged['independent_actual']:
            # an authored independent:false Work may accept it locally; it is not an independent review of this consumer
            entry.update(standing='UNREVIEWED', reason='The latest acceptance is %s, not an independent review of this consumer%s.'
                         % (judged['independence'], ' (accepted locally: its Work does not require independence)' if judged['satisfied'] else ''))
        elif judged['currentness'] == 'CURRENT' and judged['coverage']['missing']:
            # the review covered only part of what the consumer rests on: the rest is unreviewed, not changed
            local = scoped.obligation('SOURCE_CONTRACT_COVERAGE_MISSING', 'The latest independent review of %s covered %s; %s %s not reviewed.'
                                      % (consumer, ', '.join(judged['coverage']['covered']), ', '.join(judged['coverage']['missing']),
                                         'is' if len(judged['coverage']['missing']) == 1 else 'are'),
                                      subject={'consumer': consumer, 'operation': key(current)}, basis=row['source_contract']['version'],
                                      key='missing:' + ','.join(judged['coverage']['missing']))
            entry.update(standing='UNREVIEWED', changed=[], obligations=[local['id']])
            obligations.append(local)
        elif judged['currentness'] == 'CURRENT':
            entry['standing'] = 'CURRENT'
        elif judged['currentness'] == 'STALE':
            entry.update(standing='PENDING_REVIEW', changed=judged['changed_segments'])
            local = scoped.obligation('SOURCE_CONTRACT_REVIEW_STALE', judged['reason'], subject={'consumer': consumer, 'operation': key(current)},
                                      basis=row['source_contract']['version'], key=judged['reason'])
            entry['obligations'] = [local['id']]
            obligations.append(local)
        else:
            entry['standing'] = 'UNREVIEWED'
    out = {name: {**value, 'relations': sorted(value['relations']), 'segments': sorted(value['segments'])} for name, value in sorted(consumers.items())}
    publications, _ = _fold(root, owner, operation, admits)
    return detached({'schema': SCHEMA, 'operation': key(current), 'version': version(current), 'consumers': out,
                     'changed_segments': sorted({name for value in out.values() for name in value.get('changed') or ()}),
                     'obligations': scoped.merge(obligations), 'semantic_currentness': scoped.semantic_currentness(obligations),
                     'versions': sorted({row['version'] for row in publications.values()})})


def read_version(root, owner: str, operation: str, version_: str, *, admits=lambda namespace: True, select=None, budget=None) -> dict:
    """An explicit retained version through the one normalized read."""
    return read(root, normalize(reference(owner, operation, version_), select=select, budget=budget), admits=admits)
