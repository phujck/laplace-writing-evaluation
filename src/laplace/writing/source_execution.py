"""One optional Source commission, accounted in existing Writing journal metadata.

This is not a raw transport/token/currency limiter or a result replay cache.
Source owns human policy; Writing owns admitted calls and app/session reservations.
"""
from __future__ import annotations
import copy, datetime as dt, re, uuid
from pathlib import Path
from laplace.core.identity import canonical_digest
from laplace.writing import records

SCHEMA = 'laplace.source-execution/1'
LIMITS = ('max_admitted_native_invocations','max_app_admissions','max_sessions','wall_seconds')
POLICY_FIELDS = {'commission_request_id', *LIMITS}
SAFE_INTEGER = 2 ** 53 - 1  # Exact in both existing Python and browser JSON consumers.
ATTACHMENT_FIELDS = {'schema_version','commission_id','allowance_revision','project','work_id','source_grant_id','original_parent_session_id','policy'}
TERMINAL_CALLS = {'SETTLED_SUCCESS','SETTLED_REFUSAL','SETTLED_ERROR','DELIVERY_UNCERTAIN'}
ACCOUNTING_KINDS = {'writing-source-execution','writing-source-admission','writing-source-admission-binding',
    'writing-native-call-claim','writing-native-call-outcome','writing-native-call-denied','writing-source-execution-stop'}


def _now(): return dt.datetime.now(dt.timezone.utc)
def _stamp(): return _now().isoformat()
def _ident(prefix, value): return prefix + canonical_digest(value)[7:31]


class AllowanceRefused(ValueError):
    def __init__(self, reason, standing=None):
        self.source_allowance = copy.deepcopy(standing or {'state':'UNKNOWN','stop_reason':reason})
        super().__init__('Source execution refused: ' + reason)


def validate_policy(value):
    from laplace.work import development_source
    if not isinstance(value,dict) or set(value)!=POLICY_FIELDS:
        raise ValueError('native_allowance requires only commission_request_id and the four supported positive limits.')
    if not isinstance(value['commission_request_id'],str) or not re.fullmatch(r'[A-Za-z0-9._:-]{8,96}',value['commission_request_id']):
        raise ValueError('commission_request_id is an author-stable 8–96 character request identity.')
    if any(type(value[k]) is not int or not 1<=value[k]<=SAFE_INTEGER for k in LIMITS):
        raise ValueError('Source allowance limits must be positive exact JSON integers.')
    if value['wall_seconds']>development_source.MAX_LIFETIME_S or value['max_sessions']>value['max_app_admissions']:
        raise ValueError('Source wall exceeds its supported lifetime or sessions exceed app admissions.')
    return copy.deepcopy(value)


def descriptor(project,work_id,grant_id,parent_session_id,policy):
    policy=validate_policy(policy)
    account=_ident('SC-', [project,work_id,policy['commission_request_id']])
    revision=canonical_digest({'commission_id':account,'original_parent_session_id':parent_session_id,'policy':policy})
    return {'schema_version':SCHEMA,'commission_id':account,'allowance_revision':revision,'project':project,
        'work_id':work_id,'source_grant_id':grant_id,'original_parent_session_id':parent_session_id,'policy':policy}


def _checked(attachment):
    if not isinstance(attachment,dict) or set(attachment)!=ATTACHMENT_FIELDS or attachment.get('schema_version')!=SCHEMA:
        raise AllowanceRefused('invalid trusted Source execution attachment')
    expected=descriptor(attachment['project'],attachment['work_id'],attachment['source_grant_id'],attachment['original_parent_session_id'],attachment['policy'])
    if expected!=attachment:raise AllowanceRefused('Source execution attachment identity changed')
    return expected


def prepare_initial(root,project,session_id,source_grant_id):
    from laplace.work import development_source
    return development_source.execution_attachment(root,project,source_grant_id,session_id)


def _family(idx,project,ident,kind):
    """THE canonical cut-bounded record-family resolution (records._index.resolve_record_family) of one Source provenance
    identity (R2): its verified current metadata, None when this project holds no row of it, and AllowanceRefused when the
    identity is ambiguous (an immutable duplicate, a kind/project collision or a contradictory session history). No
    latest-row map answers for it; legitimate same-project session versions resolve to their current version."""
    from laplace.writing.records import _index as metadata
    try:resolved=metadata.resolve_record_family(idx,project,ident,kind=kind)
    except (metadata.AmbiguousRecord,ValueError) as error:
        raise AllowanceRefused('Source provenance identity is ambiguous: '+str(error)[:200]) from None
    return None if resolved is None else resolved['meta']


def for_turn(root,project,turn_id):
    if not turn_id:return None
    idx=records.index(root)
    try:turn=_family(idx,project,turn_id,'writing-turn')
    except AllowanceRefused:
        # An ambiguous turn that any row attaches to a Source commission is refused provenance; an ambiguous legacy turn
        # without any Source attachment keeps its unbound owner-specific admission (it was never Source authority).
        if any(row.get('source_execution') is not None for row in idx.by_id.get(turn_id,()) if row.get('record')=='writing-turn'):raise
        return None
    if turn is None:
        # Preserve unbound legacy owner-specific admission; a turn only another project holds stays refused.
        if idx.turns.get(turn_id) is not None:raise AllowanceRefused('actual project turn unavailable')
        return None
    value=turn.get('source_execution')
    if value is None:return None
    attached=_checked(value)
    session=_family(idx,project,turn.get('session_id'),'writing-session') if turn.get('session_id') else None
    if attached['project']!=project or session is None:
        raise AllowanceRefused('Source execution turn/session identity unavailable')
    admission_id=turn.get('source_admission_id')
    admission=idx.by_id.get(admission_id,())
    if len(admission)!=1 or idx.journal_id_counts.get(admission_id)!=1 or admission[0]['record']!='writing-source-admission' \
            or admission[0].get('commission_id')!=attached['commission_id'] or admission[0].get('allowance_revision')!=attached['allowance_revision']:
        raise AllowanceRefused('actual turn Source admission reservation is unavailable')
    reserved=admission[0];sid=turn['session_id']
    if reserved.get('session_id') not in (None,sid):raise AllowanceRefused('Source reservation names another session')
    if reserved.get('new_session') and session.get('source_admission_id')!=admission_id:
        raise AllowanceRefused('Source new session is not bound to its own reservation')
    bindings=[r for r in idx.by_source_admission.get(admission_id,()) if r['record']=='writing-source-admission-binding']
    if bindings and (bindings[-1].get('session_id')!=sid or bindings[-1].get('turn_id') not in (None,turn_id)):
        raise AllowanceRefused('Source turn does not match its actual reservation binding')
    return attached



def guard_spawn(root,project,*,parent_turn_id=None,reservation=None):
    """Check trusted caller AND explicit parent before a new app/session admission.

    Caller owns actual parent validation and WD/CONT authority, and calls while
    holding its existing admission lock. Replay reconciliation precedes this gate.
    """
    from laplace.writing import delivery
    parents=[]
    if parent_turn_id:
        attached=for_turn(root,project,parent_turn_id)
        if attached is not None:parents.append(attached)
    state=delivery._invocation()
    holder=(state or {}).get('native')
    if holder is not None and holder.source_scope:
        scope=holder.source_scope
        if scope[:2]!=(str(Path(root).resolve()),project):
            raise AllowanceRefused('incoming Source caller crossed project/root identity')
        attached=for_turn(root,project,scope[2])
        if attached is None:raise AllowanceRefused('incoming Source caller attachment unavailable')
        parents.append(attached)
    if reservation is None:
        if parents:raise AllowanceRefused('Source-bound execution cannot launch unsupported generic children')
        return None
    attached=_checked(reservation.get('attachment'))
    if attached['project']!=project:raise AllowanceRefused('Source reservation crossed project identity')
    if any(any(parent[k]!=attached[k] for k in
            ('commission_id','allowance_revision','original_parent_session_id')) for parent in parents):
        raise AllowanceRefused('Source spawn cannot replace its actual parent commission')
    _idx,_rows,standing,_active,reservations,bindings=_view(root,attached)
    ident=reservation.get('admission_id');reserved=reservations.get(ident)
    if reserved is None or reserved.get('role') not in {'parent','review','continuation'}:
        raise AllowanceRefused('Source spawn reservation unavailable',standing)
    actual=bindings.get(ident,reserved)
    if reservation.get('session_id') and actual.get('session_id') not in (None,reservation['session_id']):
        raise AllowanceRefused('Source spawn reservation names another session',standing)
    if standing['state']!='ACTIVE' or not standing['remaining']:
        raise AllowanceRefused('Source commission cannot admit another app turn',standing)
    return copy.deepcopy(attached)


def require_supported_spawn(root,project,turn_id,operation):
    """Only exact Source evaluator/original-parent routes inherit this commission."""
    if operation in {'dispatch_launch','dispatch_continue'} and for_turn(root,project,turn_id) is not None:
        raise AllowanceRefused('Source-bound execution cannot launch unsupported generic children')


def require_grant(root,project,grant_row,turn_id):
    if not grant_row.get('native_allowance'):return
    attached=for_turn(root,project,turn_id)
    expected=descriptor(project,grant_row['work_id'],grant_row['id'],grant_row['parent_session_id'],grant_row['native_allowance'])
    if attached is None or any(attached[k]!=expected[k] for k in ('commission_id','allowance_revision','project','work_id','original_parent_session_id')):
        raise AllowanceRefused('opted-in Source access requires its actual admitted commission attachment')


def inherit_delivery(root,project,parent_turn_id,basis,recipient):
    from laplace.work import development_source
    if not isinstance(basis,dict):raise AllowanceRefused('typed Source review basis unavailable')
    _task,grant=development_source._find_grant(root,project,basis.get('grant_id'))
    attached=for_turn(root,project,parent_turn_id)
    if attached is None:
        if grant.get('native_allowance'):
            raise AllowanceRefused('opted-in Source delivery requires its trusted original commission parent')
        return None
    development_source.validate_review_recipient(root,project,attached['work_id'],basis,recipient)
    if not grant.get('native_allowance'):raise AllowanceRefused('qualified Source grant is outside original commission')
    expected=descriptor(project,grant['work_id'],grant['id'],grant['parent_session_id'],grant['native_allowance'])
    if any(attached[k]!=expected[k] for k in ('commission_id','allowance_revision','original_parent_session_id')):
        raise AllowanceRefused('delivery cannot replace the original Source commission')
    return attached


def producer_origin(root,project,turn_id,*,armed_generation=None):
    """The actual Source producer turn from Writing records: its trusted attachment and liveness (terminal reply, Stop).

    project_work_continuity arms only while this says the producer is active, and derives Stop from it later. No payload
    label, live carrier or later caller substitutes for the recorded turn.
    """
    attached=for_turn(root,project,turn_id)
    if attached is None:raise AllowanceRefused('the turn has no Source commission attachment')
    idx=records.index(root);turn=_family(idx,project,turn_id,'writing-turn') or {}
    # R2: the terminal state reads every consumed reply of the turn through THE SAME canonical family rule (exactly one row
    # of its immutable ID in this project). A duplicate or colliding reply is ambiguous provenance and refuses (readiness
    # then holds PRODUCER_CUSTODY_UNKNOWN); it is never answered by whichever row happens to be latest.
    terminal=[]
    for row in idx.by_turn.get(turn_id,()):
        if row.get('record')!='writing-reply' or idx.project(row)!=project:continue
        reply=_family(idx,project,row.get('id'),'writing-reply') if row.get('id') else None
        if reply is None:raise AllowanceRefused('Source producer reply identity is unavailable')
        if reply.get('status') in {'completed','failed','interrupted'}:terminal.append(reply['status'])
    from laplace.writing import turn_jobs
    job=turn_jobs._JOBS.get(turn_id) or {}
    # Stop is the local job flag (this process) OR the shared exact-turn cancel marker another controller published
    # (turn_control.interrupt_turn / _publish_local_stop) OR the durable exact-turn Stop request the Writing Stop owner
    # banked before reporting success, each applied only to this turn's own generation. The durable request survives a
    # completed reply that raced the Stop and a newer turn's replacement of the shared marker; reading it appends nothing.
    # stop_custody says whether that durable answer is BOUND to one generation: an ambiguous, unbound or unreadable answer
    # is UNKNOWN (its consumer holds), never absence/READY and never a definite Stop by inference (Root 0709 B12).
    marker=_exact_stop_marker(root,turn.get('session_id'),turn_id)
    request,custody=_stop_custody(root,project,turn,turn_id,armed=armed_generation)
    live=bool(job.get('interrupt_requested')) or marker is not None
    if live and armed_generation:
        live,custody=_armed_live_stop(root,turn,turn_id,armed_generation,request,custody)
    return {'attachment':attached,'turn_id':turn_id,'session_id':turn.get('session_id'),'request_id':turn.get('request_id'),
        'terminal':terminal[-1] if terminal else None,
        'stop_requested':live or request is not None,
        'stop_marker':marker,'stop_request':request,'stop_custody':custody}


def _armed_live_stop(root,turn,turn_id,armed,request,custody):
    """(live, custody) under THE declared arming-generation rule of _stop_custody (R3). The local job flag and the exact-turn
    marker belong to the turn's CURRENT host generation, so either is the armed producer's Stop only while
    turn_control.generation_custody BINDS that same generation. Another bound generation's live Stop is not the armed
    producer's; an unbound or unreadable host leaves it unattributed: UNKNOWN (its consumer holds) unless a durable request
    already decided the custody. The terminal reply carries no generation and stays the turn's one canonical outcome."""
    from laplace.writing import turn_control
    sid=turn.get('session_id')
    host=turn_control.generation_custody(root,sid,turn_id) if sid else {'state':'UNBOUND','generation':None}
    if host['state']=='BOUND' and host.get('generation')==armed:return True,custody
    if host['state']=='BOUND' or request is not None or custody.get('state')=='STOPPED':return False,custody
    return False,{**custody,'state':'UNKNOWN','code':'LIVE_STOP_UNATTRIBUTED','armed_generation':armed,'host_record':host['state']}


def _exact_stop_marker(root,session_id,turn_id):
    """The existing exact-turn cancel marker of the session when it names THIS turn's generation, else None.

    A marker naming another turn never applies; one that records a host applies only when that is this turn's recorded
    execution host (the consumer rule turn_control states). Nothing account-wide or cross-turn is inferred.
    """
    if not session_id:return None
    from laplace.writing import child_hosts
    try:marker=child_hosts._read_host(child_hosts._host_path(root,session_id).with_suffix('.cancel.json'))
    except (ValueError,OSError):return None
    if not isinstance(marker,dict) or marker.get('turn_id')!=turn_id:return None
    if marker.get('host'):
        try:execution=child_hosts.child_execution(root,session_id) or {}
        except (ValueError,OSError):execution={}
        if execution.get('turn_id')==turn_id and execution.get('host') and execution['host']!=marker['host']:return None
    return {key:marker.get(key) for key in ('turn_id','host','requested_at','scope') if key in marker}


def _exact_stop_request(root,project,turn,turn_id):
    """The durable exact-turn Stop request (turn_control.recorded_stop_requests) of THIS turn's generation, else None.

    Same project, session and turn, and a row identity that agrees with its fields. The generation is the one
    turn_control.recorded_generation finds for this turn (the session's raw execution record, else its finished
    record, when either names the turn), the same function the Stop write used: only a request of that host generation
    applies. When neither record names the turn (newer turns replaced both), only the turn's single recorded non-null
    request generation applies. A missing, foreign or ambiguous generation gains no authority. Never another turn,
    session or the account. Read-only.
    """
    return _stop_custody(root,project,turn,turn_id)[0]


STOP_CUSTODY_STATES=('NONE','STOPPED','FOREIGN','UNKNOWN')


def _stop_custody(root,project,turn,turn_id,*,armed=None):
    """(request, custody) for the durable exact-turn Stop requests of THIS project, session and turn. Read-only.

    The request is the one row that binds a generation: the generation turn_control.generation_custody BINDS (the same
    function the Stop write used), else, once newer turns replaced both host records, the turn's ONE recorded generation.
    custody states whether that answer is bound, so an unbound answer is never read as the absence of a Stop:
      NONE     no genuine request of this project/session/turn exists;
      STOPPED  a genuine request of the generation the consumer recorded when it armed (ARMING_GENERATION: it binds
               whatever the host records say now), a genuine request of the bound generation (EXACT_GENERATION), or
               every genuine request names the one
               recorded generation while no host record names the turn (ONLY_RECORDED_GENERATION);
      FOREIGN  a host record binds the turn's current generation and every genuine request names another one (a later
               host generation of the same turn is not that Stop), or the consumer recorded its arming generation and every
               genuine request names another one (OTHER_THAN_ARMING_GENERATION: no fallback lends another generation
               the armed producer's Stop);
      UNKNOWN  genuine requests exist that no single generation binds: a request banked without a generation
               (UNBOUND_REQUEST), several recorded generations once both host records were replaced
               (AMBIGUOUS_GENERATION, the original two-real-host counterexample) or unaddressable host records
               (HOST_RECORD_UNREADABLE).
    UNKNOWN is neither absence, READY nor a definite Stop: its consumer holds. Never another turn, session or account.
    """
    session_id=turn.get('session_id')
    if not session_id:return None,{'state':'NONE','code':'NO_SESSION','requests_total':0}
    from laplace.writing import turn_control
    rows=turn_control.recorded_stop_requests(root,project,session_id,turn_id)
    if not rows:return None,{'state':'NONE','code':'NO_REQUEST','requests_total':0}
    host=turn_control.generation_custody(root,session_id,turn_id)
    named=[row.get('execution_generation') for row in rows]
    known=sorted({value for value in named if value})
    unbound=sum(not value for value in named)
    base={'requests_total':len(rows),'generations_total':len(known),'unbound_requests':unbound,
        'host_record':host['state'],'generation':host['generation'],'armed_generation':armed}
    if armed:
        matched=[row for row in rows if row.get('execution_generation')==armed]
        if matched:return matched[-1],{**base,'state':'STOPPED','code':'ARMING_GENERATION'}
        # R3: the arming generation is KNOWN, so no other generation acquires its Stop through the current-host or
        # sole-recorded-generation fallbacks below. Requests that all name other generations are FOREIGN to the armed
        # producer; a request banked without a generation stays UNKNOWN (its consumer holds).
        if unbound:return None,{**base,'state':'UNKNOWN','code':'UNBOUND_REQUEST'}
        return None,{**base,'state':'FOREIGN','code':'OTHER_THAN_ARMING_GENERATION'}
    if host['state']=='BOUND':
        matched=[row for row in rows if row.get('execution_generation')==host['generation']]
        if matched:return matched[-1],{**base,'state':'STOPPED','code':'EXACT_GENERATION'}
        if not unbound:return None,{**base,'state':'FOREIGN','code':'OTHER_GENERATION'}
    elif host['state']=='UNBOUND' and len(known)==1 and not unbound:
        matched=[row for row in rows if row.get('execution_generation')==known[0]]
        return matched[-1],{**base,'state':'STOPPED','code':'ONLY_RECORDED_GENERATION'}
    code='HOST_RECORD_UNREADABLE' if host['state']=='UNREADABLE' else 'UNBOUND_REQUEST' if unbound else 'AMBIGUOUS_GENERATION'
    return None,{**base,'state':'UNKNOWN','code':code}


def account_capacity(root,attachment,*,apps,sessions):
    """(standing, SUFFICIENT|UNKNOWN|CLOSED, reason) for a planned chain of app admissions and new sessions.

    The same predicates reserve_app enforces; this only reads. UNKNOWN custody is never treated as capacity.
    """
    standing=status(root,attachment)
    if standing.get('state')=='UNKNOWN':return standing,'UNKNOWN','account custody is UNKNOWN (%s); no admission is inferred'%standing.get('stop_reason')
    if standing.get('state')!='ACTIVE':return standing,'CLOSED','account is %s (%s)'%(standing.get('state'),standing.get('stop_reason'))
    if not standing.get('remaining'):return standing,'CLOSED','no admitted native invocation remains'
    if (standing.get('app_remaining') or 0)<apps or (standing.get('session_remaining') or 0)<sessions:
        return standing,'CLOSED','planned %d app admission(s) and %d session(s) exceed the remaining %s/%s'%(
            apps,sessions,standing.get('app_remaining'),standing.get('session_remaining'))
    return standing,'SUFFICIENT',None


def prepared_inheritance(root,project,origin,basis,recipient):
    """The ONE narrow trusted-origin resolution of a recorded completion intent (work_delivery.submit_prepared).

    It resolves the ORIGINAL producer turn's commission again through inherit_delivery and requires it to equal the
    attachment recorded when the producer armed the intent. The dispatcher's own turn, door or labels play no part,
    and ordinary inherit_delivery refusals for unattached callers are unchanged.
    """
    attached=inherit_delivery(root,project,(origin or {}).get('turn_id'),basis,recipient)
    if attached is None or attached!=(origin or {}).get('source_execution'):
        raise AllowanceRefused('the recorded producer origin no longer resolves to its original commission')
    return attached


def _rows(root,attachment):
    idx,rows=records.source_execution_metadata(root,attachment['project'],attachment['commission_id'])
    # Accounting identities are immutable. WS/WT rows use their existing latest
    # generation projection instead of treating a legitimate session update as
    # a duplicate claim. Audit/content rows do not define account standing.
    accounting=[r for r in rows if r['record'] in ACCOUNTING_KINDS]
    if any(idx.journal_id_counts.get(r.get('id'),0)!=1 for r in accounting):
        raise AllowanceRefused('ambiguous Source accounting custody')
    projected={}
    for row in rows:
        view=idx.sessions if row['record']=='writing-session' else idx.turns if row['record']=='writing-turn' else None
        if view is not None:
            current=view.get(row['id'])
            if current and current.get('commission_id')==attachment['commission_id']:
                projected[(row['record'],row['id'])]=current
    return idx,sorted([*accounting,*projected.values()],key=lambda r:r['_order'])


def _view(root,attachment):
    attached=_checked(attachment);idx,rows=_rows(root,attached);policy=attached['policy']
    headers=[r for r in rows if r['record']=='writing-source-execution']
    if len(headers)>1:raise AllowanceRefused('ambiguous Source commission header')
    header=headers[0] if headers else None
    if rows and header is None:raise AllowanceRefused('Source accounting header unavailable')
    if header and (header.get('allowance_revision')!=attached['allowance_revision'] or header.get('policy')!=policy):
        raise AllowanceRefused('immutable Source allowance policy changed')
    if any(r.get('allowance_revision')!=attached['allowance_revision'] for r in rows):
        raise AllowanceRefused('Source accounting revision custody changed')
    claims={r['id']:r for r in rows if r['record']=='writing-native-call-claim'}
    if sorted(r.get('ordinal',0) for r in claims.values())!=list(range(1,len(claims)+1)):
        raise AllowanceRefused('Source claim ordinal custody is incomplete or ambiguous')
    outcomes={}
    for r in rows:
        if r['record']=='writing-native-call-outcome':outcomes[r.get('claim_id')]=r
    reservations={r['id']:r for r in rows if r['record']=='writing-source-admission'}
    bindings={}
    for r in rows:
        if r['record']=='writing-source-admission-binding':bindings[r['admission_id']]=r
    sessions=set();unknown_sessions=set()
    for ident,r in reservations.items():
        selected=bindings.get(ident,r);sid=selected.get('session_id')
        if sid:sessions.add(sid)
        elif r.get('new_session'):unknown_sessions.add(ident)
    stops=[r for r in rows if r['record']=='writing-source-execution-stop']
    unknown={r.get('claim_id') for r in stops if r.get('reason_code')=='CLAIM_PUBLICATION_UNKNOWN'}-set(claims)
    spent=len(claims)+len(unknown)
    active=[r for ident,r in claims.items() if outcomes.get(ident,{}).get('state') not in TERMINAL_CALLS]
    remaining=max(0,policy['max_admitted_native_invocations']-spent)
    deadline=header.get('deadline_at') if header else None
    expired=bool(deadline and _now()>=dt.datetime.fromisoformat(deadline))
    state,reason=('READY',None) if not header else ('ACTIVE',None)
    if remaining==0:state,reason='DRAINING','NATIVE_ALLOWANCE_EXHAUSTED'
    if expired:state,reason='DRAINING','COMMISSION_WALL_EXPIRED'
    if stops:state,reason=('UNKNOWN' if stops[-1]['reason_code'] in {'CLAIM_PUBLICATION_UNKNOWN','SETTLEMENT_PUBLICATION_UNKNOWN','SESSION_CREATION_UNKNOWN'} else 'STOPPED'),stops[-1]['reason_code']
    from laplace.writing import turn_jobs
    if any((turn_jobs._JOBS.get(r['id']) or {}).get('source_execution_unknown') for r in rows if r['record']=='writing-turn'):
        state,reason='UNKNOWN','ACCOUNT_CUSTODY_UNKNOWN'
    public={'commission_id':attached['commission_id'],'state':state,'admitted':len(claims),'remaining':remaining,
        'active':len(active),'denied':sum(r['record']=='writing-native-call-denied' for r in rows),
        'app_admissions':len(reservations),'app_remaining':max(0,policy['max_app_admissions']-len(reservations)),
        'sessions':len(sessions)+len(unknown_sessions),'session_remaining':max(0,policy['max_sessions']-len(sessions)-len(unknown_sessions)),
        'deadline_at':deadline,'stop_reason':reason,'read':read_handle(attached)}
    return idx,rows,public,active,reservations,bindings


def read_handle(attachment):
    """Existing read-only Source status operation; human POST adds live accounting outside its cut."""
    payload={'action':'status','work_id':attachment['work_id']}
    return {'operation':'development_source','payload':payload,
        'http':{'method':'POST','url':'/work/development','payload':{'project':attachment['project'],**payload}}}


def status(root,attachment):
    try:return copy.deepcopy(_view(root,attachment)[2])
    except (ValueError,OSError) as error:
        return {'commission_id':attachment.get('commission_id') if isinstance(attachment,dict) else None,
            'state':'UNKNOWN','remaining':0,'active':None,'stop_reason':'ACCOUNT_CUSTODY_UNKNOWN'}


def _base_row(attachment,record,ident):
    return {'record':record,'id':ident,'project':attachment['project'],'work_id':attachment['work_id'],
        'commission_id':attachment['commission_id'],'allowance_revision':attachment['allowance_revision'],'ts':_stamp()}


def _exact(root,ident,expected):
    idx=records.index(root);rows=idx.by_id.get(ident,())
    if idx.journal_id_counts.get(ident)!=1 or len(rows)!=1:return False
    try:row=records.raw_indexed_record(idx,rows[0])
    except (ValueError,OSError):return False
    return all(row.get(k)==v for k,v in expected.items() if k!='ts')


def _bank(root,row):
    try:records.bank(Path(root),row)
    except Exception:
        if not _exact(root,row['id'],row):raise


def _open(root,attached):
    _idx,rows,_standing,*_= _view(root,attached)
    if not any(r['record']=='writing-source-execution' for r in rows):
        row={**_base_row(attached,'writing-source-execution',attached['commission_id']),
            'policy':copy.deepcopy(attached['policy']),'source_grant_id':attached['source_grant_id'],
            'original_parent_session_id':attached['original_parent_session_id'],'commission_request_id':attached['policy']['commission_request_id'],
            'opened_at':_stamp(),'deadline_at':(_now()+dt.timedelta(seconds=attached['policy']['wall_seconds'])).isoformat()}
        _bank(root,row)


def reserve_app(root,attachment,request_id,*,session_id=None,new_session=False,role='parent'):
    from laplace.work import project_work
    attached=_checked(attachment)
    if role not in {'parent','review','continuation'} or not isinstance(request_id,str) or not request_id:
        raise AllowanceRefused('invalid Source app reservation identity')
    if role in {'parent','continuation'} and (new_session or session_id!=attached['original_parent_session_id']):
        raise AllowanceRefused('Source parent admission must retain its exact original session')
    ident=_ident('SA-', [attached['commission_id'],request_id])
    with project_work.dispatch_lock(root):
        _open(root,attached);idx,rows,standing,_active,reservations,bindings=_view(root,attached)
        prior=reservations.get(ident)
        was_reserved=prior is not None
        if prior:
            proved_session=bindings.get(ident,prior).get('session_id')
            if not proved_session and session_id and (idx.sessions.get(session_id) or {}).get('source_admission_id')==ident:
                proved_session=session_id
            recovered_creation=bool(prior.get('new_session') and not new_session and session_id and proved_session==session_id)
            if (prior.get('request_sha256')!=canonical_digest(request_id) or prior.get('role')!=role
                    or prior.get('new_session')!=new_session and not recovered_creation
                    or session_id and proved_session not in (None,session_id)):
                raise AllowanceRefused('Source app request already reserves different intent',standing)
        else:
            if standing['state']!='ACTIVE' or not standing['remaining'] or not standing['app_remaining']:
                raise AllowanceRefused('Source commission cannot admit another app turn',standing)
            known={r.get('session_id') for r in reservations.values()}|{r.get('session_id') for r in bindings.values()}
            if (new_session or session_id not in known) and not standing['session_remaining']:
                raise AllowanceRefused('Source session allowance exhausted',standing)
            prior={**_base_row(attached,'writing-source-admission',ident),'admission_id':ident,
                'request_id':request_id[:96],'request_sha256':canonical_digest(request_id),
                'session_id':session_id,'new_session':bool(new_session),'role':role}
            _bank(root,prior)
        actual=bindings.get(ident,prior)
        # The actual Writing session/turn can survive a lost acknowledgement before bind_app.
        related=idx.by_source_admission.get(ident,())
        turns=list({r['id']:idx.turns[r['id']] for r in related if r['record']=='writing-turn'
            and idx.turns[r['id']].get('source_admission_id')==ident}.values())
        sessions=list({r['id']:idx.sessions[r['id']] for r in related if r['record']=='writing-session'
            and idx.sessions[r['id']].get('source_admission_id')==ident}.values())
        if len(turns)>1 or len(sessions)>1:raise AllowanceRefused('ambiguous actual Source app admission',standing)
        sid=actual.get('session_id') or (sessions[-1]['id'] if sessions else None)
        may_create=bool(new_session and not was_reserved and sid is None)
        if new_session and was_reserved and sid is None:
            stop(root,attached,'SESSION_CREATION_UNKNOWN')
            raise AllowanceRefused('SESSION_CREATION_UNKNOWN',status(root,attached))
        return {'attachment':attached,'admission_id':ident,'session_id':sid,'may_create_session':may_create,
            'turn_id':actual.get('turn_id') or (turns[-1]['id'] if turns else None),'deadline_at':standing['deadline_at']}


def bind_app(root,reservation,session_id,turn_id=None):
    from laplace.work import project_work
    attached=_checked(reservation['attachment']);ident=reservation['admission_id']
    with project_work.dispatch_lock(root):
        _idx,_rows,standing,_active,reservations,bindings=_view(root,attached)
        if ident not in reservations:raise AllowanceRefused('Source app reservation unavailable',standing)
        prior=bindings.get(ident)
        if prior and (prior.get('session_id')!=session_id or turn_id and prior.get('turn_id') not in (None,turn_id)):
            raise AllowanceRefused('Source app reservation already bound elsewhere',standing)
        if prior and prior.get('turn_id')==turn_id:
            return {**copy.deepcopy(reservation),'session_id':session_id,'turn_id':turn_id}
        row={**_base_row(attached,'writing-source-admission-binding','SAB-'+uuid.uuid4().hex),
            'admission_id':ident,'session_id':session_id,'turn_id':turn_id}
        _bank(root,row)
    return {**copy.deepcopy(reservation),'session_id':session_id,'turn_id':turn_id}


def stop(root,attachment,reason):
    from laplace.work import project_work
    attached=_checked(attachment)
    with project_work.dispatch_lock(root):
        _bank(root,{**_base_row(attached,'writing-source-execution-stop','SS-'+uuid.uuid4().hex),'reason_code':str(reason)[:80]})
    return status(root,attached)


def control(root,project,turn_id):
    try:attached=for_turn(root,project,turn_id)
    except (ValueError,OSError):return {'state':'UNKNOWN','stop':True,'reason':'ACCOUNT_CUSTODY_UNKNOWN','active_for_turn':None}
    if attached is None:return None
    from laplace.writing import turn_jobs
    if (turn_jobs._JOBS.get(turn_id) or {}).get('source_execution_unknown'):
        return {'state':'UNKNOWN','stop':True,'reason':'ACCOUNT_CUSTODY_UNKNOWN','active_for_turn':None}
    try:
        _idx,_rows,standing,active,*_=_view(root,attached)
        own=sum(r.get('turn_id')==turn_id for r in active)
        return {**standing,'active_for_turn':own,'stop':standing['state'] in {'STOPPED','UNKNOWN'} or
            standing['stop_reason']=='COMMISSION_WALL_EXPIRED' or standing['state']=='DRAINING' and not active,
            'reason':standing['stop_reason']}
    except (ValueError,OSError):return {'state':'UNKNOWN','stop':True,'reason':'ACCOUNT_CUSTODY_UNKNOWN','active_for_turn':None}


def _wire_digest(intent):
    try:return canonical_digest(intent)
    except (TypeError,ValueError):return canonical_digest({'unsupported_input_type':type(intent).__name__})


def _mark_runtime_unknown(root,turn_id,reason):
    # Existing job supervision flag, never a count/authority store. Durable custody
    # remains the journal; total storage outage cannot fabricate a persisted stop.
    from laplace.writing import turn_jobs
    job=turn_jobs._JOBS.get(turn_id)
    if job is not None:job['source_execution_unknown']=reason
    try:idx=records.index(root)
    except (ValueError,OSError):return
    commission=(idx.turns.get(turn_id,{}).get('source_execution') or {}).get('commission_id')
    for ident,job in list(turn_jobs._JOBS.items()):
        account=(idx.turns.get(ident,{}).get('source_execution') or {}).get('commission_id')
        if ident==turn_id or commission and account==commission:job['source_execution_unknown']=reason


def claim_native(root,project,turn_id,holder,intent):
    from laplace.work import project_work
    attached=for_turn(root,project,turn_id)
    if attached is None:return None
    scope=(str(Path(root).resolve()),project,turn_id)
    if holder.source_scope is not None:
        if holder.source_scope!=scope:raise AllowanceRefused('private native holder crossed execution identity')
        if holder.source_denied or holder.source_unknown or not holder.source_admitted:raise AllowanceRefused('incoming Source claim was not admitted',status(root,attached))
        if holder.original_wire_sha256!=_wire_digest(intent):raise AllowanceRefused('private incoming intent changed')
        if holder.source_settled is not None or holder.source_pending_outcome is not None:raise AllowanceRefused('incoming dispatch already settled; a later arrival needs a fresh holder')
        return holder.source_claim
    holder.source_scope=scope;holder.source_attachment=attached
    # Grammar normalization never changes this original incoming wire identity.
    wire=_wire_digest(intent)
    holder.original_wire_sha256=wire
    ident=_ident('NC-', [attached['commission_id'],holder.native_invocation_id]);holder.source_claim=ident
    with project_work.dispatch_lock(root):
        _idx,_rows,standing,_active,_res,_bindings=_view(root,attached)
        idx=records.index(root)
        terminal=any(r['record']=='writing-reply' and r.get('status') in {'completed','failed','interrupted'} for r in idx.by_turn.get(turn_id,()))
        from laplace.writing import turn_jobs
        job=turn_jobs._JOBS.get(turn_id)
        runtime_unknown=bool(job and job.get('source_execution_unknown'))
        if standing['state']!='ACTIVE' or not standing['remaining'] or terminal or runtime_unknown:
            row={**_base_row(attached,'writing-native-call-denied','ND-'+uuid.uuid4().hex),
                'turn_id':turn_id,'native_invocation_id':holder.native_invocation_id,'reason_code':'TURN_NOT_ACTIVE' if terminal else 'ACCOUNT_CUSTODY_UNKNOWN' if runtime_unknown else standing['stop_reason'] or 'ACCOUNT_NOT_ACTIVE'}
            _bank(root,row);holder.source_denied=True
            raise AllowanceRefused(row['reason_code'],status(root,attached))
        idx=records.index(root);turn=idx.turns[turn_id]
        row={**_base_row(attached,'writing-native-call-claim',ident),'claim_id':ident,
            'turn_id':turn_id,'session_id':turn['session_id'],'native_invocation_id':holder.native_invocation_id,
            'original_wire_sha256':wire,'ordinal':standing['admitted']+1,'state':'CLAIMED',
            'transport_kind':holder.transport_kind,'transport_epoch':holder.transport_epoch,
            'transport_request_digest':canonical_digest(holder.transport_request_id)}
        try:_bank(root,row)
        except Exception as error:
            holder.source_unknown=True
            _mark_runtime_unknown(root,turn_id,'CLAIM_PUBLICATION_UNKNOWN')
            try:_bank(root,{**_base_row(attached,'writing-source-execution-stop','SS-'+uuid.uuid4().hex),
                'claim_id':ident,'reason_code':'CLAIM_PUBLICATION_UNKNOWN'})
            except Exception:pass
            raise AllowanceRefused('CLAIM_PUBLICATION_UNKNOWN',{**status(root,attached),'state':'UNKNOWN','remaining':0,'stop_reason':'CLAIM_PUBLICATION_UNKNOWN'}) from error
    holder.source_admitted=True
    return ident


def settle_native(root,holder,outcome):
    if not holder.source_claim or not holder.source_admitted or holder.source_denied or holder.source_unknown:return
    from laplace.work import project_work
    attached=holder.source_attachment
    if outcome not in TERMINAL_CALLS:raise ValueError('unsupported native settlement')
    # The transport owns the same incoming holder until its response has actually
    # encoded/sent. Its durable claim stays active, including the final slot.
    if holder.delivery_owned:
        if holder.source_pending_outcome!='DELIVERY_UNCERTAIN':holder.source_pending_outcome=outcome
        return
    if holder.source_settled==outcome:return
    with project_work.dispatch_lock(root):
        row={**_base_row(attached,'writing-native-call-outcome','NO-'+uuid.uuid4().hex),
            'claim_id':holder.source_claim,'native_invocation_id':holder.native_invocation_id,
            'turn_id':holder.source_scope[2],'state':outcome}
        try:_bank(root,row)
        except Exception:
            holder.source_unknown=True
            _mark_runtime_unknown(root,holder.source_scope[2],'SETTLEMENT_PUBLICATION_UNKNOWN')
            try:stop(root,attached,'SETTLEMENT_PUBLICATION_UNKNOWN')
            except Exception:pass
            return
        holder.source_settled=outcome
