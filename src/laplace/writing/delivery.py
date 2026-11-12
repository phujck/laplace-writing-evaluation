"""THE SHARED TOOL DELIVERY BOUNDARY (shared-delivery grant, 2026-10-19; Root decision on WORK-source-state-work-repair).

Responsibility map of one native call (request -> model text):
  0. writing_tools.call opens ONE ``invocation``: the contract every stage of this call reads. Both offered spellings,
     the named {operation, payload} and the semantic {verb, concept, target, expected, payload, by}, resolve through the
     existing admission, guards and owner translation to one admitted act; writing_tools._execute_operation (the one
     dispatch both reach) records it with ``admit_act``: the resolved operation and payload, their delivery ``profile``
     and the original attribution. A refusal before dispatch records the act the route named. The first act recorded
     is the act of the invocation; the final admission reads it, never the syntax of the original call.
  1. ``profile(operation, payload)`` is what an owner declares for that act (PROFILE_OWNERS); this module imports no
     domain budget and no domain imports a tool door. Unprofiled acts keep their declared contracts.
  2. For a bounded act, ``planned(line=...)`` gives the owner the line its semantic result must fit: the declared bound
     minus (a) the exact bytes of the door's mandatory metadata (review_read, read_receipt), (b) the exact bytes of the
     outer grammar envelope the semantic spelling wraps around the owner result (``declare_envelope`` by
     writing_tools.request before the owner call; ``wrapped`` measures it), and (c) the largest bounded form of every
     late addition this result may have to carry, each from its owner's own composer and without effects
     (writing_tools._plan_additions): the deferred context refresh (turn_reads.pending_refresh_notice), the author-update
     offer without bodies (provider_updates.author_offer(bank=False) + author_notice), the deferred input notice and the
     input owner's bounded failure answers (provider_updates.pending_input), the custody diagnostic without its identity
     list and the update-delivery-unavailable answer (error texts bounded by ``bounded_text``). THE CUT: the same plan
     fixes which mutable offers belong to this delivery (``record_cut``): the correction ids and the input control
     (sequence, control id) observed before the page is selected. The owner then chooses its projection (rows, notices,
     order, cut) and reports it with ``record_projection``; the projection is semantic identity, not transport.
  3. writing_tools._receipt_turn_read banks the read row WITH that projection, so the receipt binds exactly the consulted
     projection. Every later addition is then DECIDED before its effects by ``fits``: its exact candidate, inside the
     declared envelope and beside the reserved forms of the additions still to come, must leave the final envelope
     admissible. A context refresh that does not fit is not adopted (turn_reads.deferred_refresh, no baseline);
     author-update bodies that do not fit are offered as author_notice (the same banked offer, ids and required reads);
     an input whose exact publication (with the largest maintenance warning) does not fit stays PREPARED
     (provider_updates.turn_input_offer space guard: no baseline, delivery row, receipt or frontier advance) and its
     deferred notice is delivered. Offers outside the cut (a correction or an input admitted after planning) are not
     offered, banked, prepared, acknowledged or adopted by this delivery; the next boundary plans them.
  4. Every pure replay of a consumed read (proposal_currentness, turn_reads baselines and context coverage, failure
     recovery diagnostics) goes through writing_tools.replay_read, which runs the owner under ``planned(replay=...)``
     with the retained projection: no banking, no publication, no acknowledgement, no context refresh. A legacy read row
     without a projection replays as before (the owner's own default line), explicitly.
  5. writing_tools.call and writing_tools.tool_failure compose the complete result (receipt, context refresh, custody
     diagnostic, author updates, turn input) and pass it to ``admit`` with the act's profile. ``admit`` measures the
     model text (``emitted``, writing_sources.content_text) and, only when over the bound, projects the two parts that
     are not decided by a stage: the help contract's request echo on a refusal (its recovery: help and failure_read) and
     the custody identity list (status, counts and bytes stay). Published content is never trimmed afterwards. Under the
     plan of step 2 every reserved form fits by construction; ``delivery_bound`` still says so truthfully if an unplanned
     shape exceeds. One pass, a fixed order, no retry and no storage of full responses.
  6. writing_sources.content_items/content_text serialize the text and media; the outer RPC framing (MCP stdio, Codex) is
     transport, measured separately.
Operations and variants without a declared profile (intentional full reads included) keep their declared contracts.
"""
from __future__ import annotations

import contextlib
import contextvars
import uuid
from pathlib import Path
import copy
import importlib

#: operation -> "module:function(payload) -> {'bound': int} | None": the owner declares which variants are bounded
PROFILE_OWNERS = {'project': 'laplace.work.project_work_views:delivery_profile',
                  'development_source': 'laplace.work.development_source:delivery_profile',
                  'work_review': 'laplace.work.project_work_review:delivery_profile'}

_PLAN: contextvars.ContextVar = contextvars.ContextVar('writing_delivery_plan', default=None)
_INVOCATION: contextvars.ContextVar = contextvars.ContextVar('writing_delivery_invocation', default=None)
_INCOMING: contextvars.ContextVar = contextvars.ContextVar('writing_native_incoming', default=None)


class _Incoming:
    """Private one-arrival identity. Never accepted from JSON/schema fields or RPC IDs."""
    def __init__(self, transport_kind='direct-internal', transport_epoch=None, request_id=None):
        self.native_invocation_id = uuid.uuid4().hex
        self.transport_kind = transport_kind
        self.transport_epoch = str(transport_epoch)[:96] if transport_epoch is not None else None
        self.transport_request_id = request_id
        self.depth = 0
        self.source_scope = self.source_attachment = self.source_claim = None
        self.source_denied = self.source_unknown = self.source_admitted = False
        self.source_settled = None
        self.source_pending_outcome = None
        self.delivery_owned = False
        self.original_wire_sha256 = None


@contextlib.contextmanager
def incoming(*, transport_kind='direct-internal', transport_epoch=None, request_id=None):
    holder = _Incoming(transport_kind, transport_epoch, request_id)
    token = _INCOMING.set(holder)
    holder.delivery_owned = True
    try:
        yield holder
    except BaseException:
        delivery_uncertain(holder)
        raise
    finally:
        holder.delivery_owned = False
        try:
            if holder.source_pending_outcome is not None and holder.source_scope:
                from laplace.writing import source_execution
                source_execution.settle_native(Path(holder.source_scope[0]),holder,holder.source_pending_outcome)
        finally:
            _INCOMING.reset(token)


def delivery_uncertain(holder):
    """Adapter encoding/send failure belongs to its same spent incoming claim."""
    if not isinstance(holder,_Incoming) or not holder.source_scope:
        return
    from laplace.writing import source_execution
    source_execution.settle_native(Path(holder.source_scope[0]),holder,'DELIVERY_UNCERTAIN')


def late_forms():
    inv = _invocation()
    holder = inv.get('native') if inv else None
    if not holder or not holder.source_attachment:
        return {}
    # Maximum supported scalar widths, declared before owner projection/addition effects.
    from laplace.writing import source_execution
    number = 9007199254740991
    return {'source_allowance': {'commission_id': 'SC-' + 'f' * 24, 'state': 'DRAINING',
        'admitted': number, 'remaining': number, 'active': number, 'denied': number,
        'app_admissions': number, 'app_remaining': number, 'sessions': number, 'session_remaining': number,
        'deadline_at': '9999-12-31T23:59:59.999999+00:00', 'stop_reason': 'X' * 80,
        'read':source_execution.read_handle(holder.source_attachment)}}



@contextlib.contextmanager
def invocation(carried=None, *, incoming=None):
    """ONE native call (writing_tools.call): the door declares the envelope its result is wrapped in, the dispatch
    records the admitted act with its profile, the plan records the eligible-offer cut and the reserved forms, and the
    final admission reads them (module text, step 0). ``carried`` is the state an owner exception carried out of the
    call it escaped (``carry``): the failure owner finishes that same act under it, with no envelope (the failure body
    is the transport's own error channel) and without touching any other call."""
    current = _INVOCATION.get()
    if current is not None and carried is None and incoming is None:
        yield current
        return
    holder = incoming or (carried or {}).get('native') or _INCOMING.get() or _Incoming()
    if not isinstance(holder, _Incoming):
        raise ValueError('Native incoming holder is private gateway state.')
    state = ({'envelope': None, 'act': copy.deepcopy(carried['act']), 'cut': copy.deepcopy(carried['cut']),
              'reserved': copy.deepcopy(carried['reserved']), 'native': holder} if carried else
             {'envelope': None, 'act': None, 'cut': None, 'reserved': None, 'native': holder})
    token = _INVOCATION.set(state)
    try:
        yield state
    finally:
        _INVOCATION.reset(token)


def _invocation():
    return _INVOCATION.get()


_CARRIED = '_laplace_delivery_invocation'


def carry(error, state):
    """An owner exception leaving the call carries the invocation's admitted act, cut and reserved forms on itself
    (never on module state), so the existing exception-to-failure handoff finishes the same act."""
    setattr(error, _CARRIED, {**{key: copy.deepcopy(state.get(key)) for key in ('act', 'cut', 'reserved')},
                             'native': state.get('native')})
    return error


def carried(error):
    """The invocation state an exception carries, or None for an exception raised outside any native call."""
    return getattr(error, _CARRIED, None)


def declare_envelope(template, key):
    """The outer grammar envelope the door wraps around the owner result (the result lands at ``key`` of ``template``),
    declared before the owner call so the plan counts it. A no-op outside an invocation."""
    inv = _invocation()
    if inv is not None and inv['envelope'] is None:
        inv['envelope'] = {'template': copy.deepcopy(template), 'key': key}


def envelope():
    inv = _invocation()
    return None if inv is None else inv['envelope']


def admit_act(operation, payload, **attribution):
    """The admitted canonical act of this invocation: its resolved operation and payload, their delivery profile and
    the original attribution. The first act recorded is the invocation's (an act refused before dispatch, or the one
    dispatch both spellings reach); it is returned to every later caller. Outside an invocation the act is returned
    unrecorded."""
    act = {'operation': str(operation or ''), 'payload': dict(payload or {}), 'profile': profile(operation, payload), **attribution}
    inv = _invocation()
    if inv is None:
        return act
    if inv['act'] is None:
        inv['act'] = act
    return inv['act']


def current_act():
    inv = _invocation()
    return None if inv is None else inv['act']


def record_cut(cut, reserved):
    """The eligible-offer cut and the reserved forms of this invocation's plan (module text, step 2)."""
    inv = _invocation()
    if inv is not None and inv['cut'] is None:
        inv['cut'] = cut
        inv['reserved'] = dict(reserved)


def cut():
    inv = _invocation()
    return None if inv is None else inv['cut']


def reserved():
    """The reserved forms of the additions this invocation has not decided yet (settled ones are in the result)."""
    inv = _invocation()
    return None if inv is None else inv['reserved']


def settle(field):
    """A stage has decided ``field`` (its value, or nothing, is now in the result): its reserved form is released."""
    inv = _invocation()
    if inv is not None and inv['reserved'] is not None:
        inv['reserved'].pop(field, None)


def profile(operation, payload):
    """The bounded delivery profile an owner declares for this exact request, or None (its declared full contract)."""
    owner = PROFILE_OWNERS.get(str(operation or ''))
    if owner is None or not isinstance(payload, dict):
        return None
    module, function = owner.split(':')
    return getattr(importlib.import_module(module), function)(payload)


@contextlib.contextmanager
def planned(*, line=None, replay=None):
    """The delivery plan of one owner call: a line to fit (a bounded native read) or a retained projection to reproduce
    (a pure replay). The owner records the projection it delivered into the plan."""
    plan = {'line': line, 'replay': replay, 'projection': None}
    token = _PLAN.set(plan)
    try:
        yield plan
    finally:
        _PLAN.reset(token)


def owner_line():
    plan = _PLAN.get()
    return None if plan is None else plan.get('line')


def owner_replay():
    plan = _PLAN.get()
    return None if plan is None else plan.get('replay')


def record_projection(part, value):
    """Owners report each part of the semantic projection they delivered (a page, an embedded preview); the receipt
    retains them as {part: projection} for exact replay."""
    plan = _PLAN.get()
    if plan is not None and plan.get('replay') is None:
        plan['projection'] = {**(plan.get('projection') or {}), part: copy.deepcopy(value)}


def emitted(value) -> int:
    """Bytes of the model text both native doors emit for this value (writing_sources.content_text)."""
    from laplace.projects.writing_sources import content_text
    return len(content_text(value).encode('utf-8'))


def inserted(value: dict, added: dict) -> int:
    """Exact bytes ``added`` keys cost when inserted into the non-empty dict ``value`` (as content_text emits them); the
    cost of a key is the same at every level of nesting, so one measure serves the owner result and its envelope."""
    probe = value or {'owner': 0}
    return emitted({**probe, **added}) - emitted(probe)


def wrapped(envelope) -> int:
    """Exact bytes an envelope adds around the result placed at its key (0 without an envelope)."""
    if not envelope:
        return 0
    probe = {'owner': 0}
    return emitted({**envelope['template'], envelope['key']: probe}) - emitted(probe)


def enveloped(value, envelope, outer=None):
    """``value`` inside ``envelope`` (or itself without one) with the outer-level additions ``outer`` beside it."""
    if envelope:
        return {**envelope['template'], envelope['key']: value, **(outer or {})}
    return {**value, **(outer or {})}


def bounded_text(text, nbytes: int = 500) -> str:
    """At most ``nbytes`` of model text of a string (as content_text emits it, without its quotes), cut on a character:
    THE ONE BOUND of every error text a late owner answer delivers, so each such answer has an exact largest form."""
    text = str(text)[:nbytes]
    from laplace.projects.writing_sources import content_text
    while text and len(content_text(text).encode('utf-8')) - 2 > nbytes:
        text = text[:-1]
    return text


def _project_contract(value, reads):
    contract = value.get('contract')
    if not isinstance(contract, dict):
        return None
    echoed = [key for key in ('example', 'native') if key in contract]
    if not echoed:
        return None
    return {**value, 'contract': {**{k: v for k, v in contract.items() if k not in echoed},
            'omitted': {'fields': echoed, 'says': 'Request echoes omitted at delivery; the original request is the failure_read and the '
                        'contract is the help read.', 'reads': reads}}}


def _project_custody(value, reads):
    """The owner's custody diagnostic (core.bodies.degradation) without its identity list: status, counts and bytes
    stay; the identities are counted into identities_omitted. No exact read retains them, and the note says so."""
    custody = value.get('custody_degradation')
    if not isinstance(custody, dict) or not custody.get('identities'):
        return None
    return {**value, 'custody_degradation': {**{k: v for k, v in custody.items() if k != 'identities'},
            'identities_omitted': int(custody.get('identities_omitted') or 0) + len(custody['identities']),
            'identities_note': 'Body identities omitted at delivery; no exact read retains them.'}}


#: the projectable parts, in the fixed order ``admit`` applies them (each has an exact existing recovery or says it has none)
PROJECTIONS = (('contract', _project_contract), ('custody_degradation', _project_custody))


def admit(result, bound_profile):
    """The final delivery admission of one complete result (see the module text). Returns the result to deliver."""
    if not bound_profile or not isinstance(result, dict):
        return result
    bound = bound_profile['bound']
    if emitted(result) <= bound:
        return result
    reads = [read for read in (result.get('help'), result.get('failure_read')) if read]
    value, projected = result, []
    for name, project in PROJECTIONS:   # one pass, fixed order, each re-measured
        candidate = project(value, reads)
        if candidate is not None:
            value, projected = candidate, projected + [name]
            if emitted(value) <= bound:
                break
    note = {'bound': bound, 'projected': projected}
    delivered = _noted(value, note)
    if note['emitted'] > bound:
        mandatory = [key for key in ('read_receipt', 'context_refresh', 'custody_degradation', 'author_updates', 'turn_input',
                                     'failure_receipt', 'error') if key in value]
        note.update(exceeded=True, mandatory=mandatory,
                    says='The parts this delivery may not project (receipted result, receipts, decided additions, diagnostics) exceed the bound.')
        delivered = _noted(value, note)
    return delivered


def admissible(value, bound_profile) -> bool:
    """Whether ``value`` is delivered within its profile's bound by ``admit`` (after its projections)."""
    return not bound_profile or not (admit(value, bound_profile).get('delivery_bound') or {}).get('exceeded')


def fits(result, field, candidate, bound_profile, later=None, envelope=None) -> bool:
    """A stage's decision before its effects: does ``candidate`` as ``result[field]``, inside the declared ``envelope``
    and beside the reserved forms of the additions still to come (``later``, by field), leave the final envelope
    admissible?"""
    pending = {key: value for key, value in (later or {}).items() if value is not None and key not in result and key != field}
    return admissible(enveloped({**result, field: candidate}, envelope, pending), bound_profile)


def _noted(value, note):
    """``value`` with its delivery note, whose ``emitted`` is the size of the delivered text INCLUDING the note: a fixed
    point over the digit count of that one number, reached in at most three measurements."""
    note['emitted'] = 0
    for _ in range(3):
        size = emitted({**value, 'delivery_bound': note})
        if size == note['emitted']:
            break
        note['emitted'] = size
    return {**value, 'delivery_bound': note}
