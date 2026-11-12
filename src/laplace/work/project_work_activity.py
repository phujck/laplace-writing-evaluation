"""Qualified execution observations of Work: one shape for in-app and external activity (Sol D2-A).

Ownership
  A section of the project_work owner. In-app activity is read from its own owner at read time,
  ``writing.turn_jobs.work_activity`` (accepted turn starts, live turns and child hosts that name a Work);
  nothing in-app is stored here. External activity exists only as ``project-work-observation`` rows of the
  Work ledger (``corpus_friction/work_orders.jsonl``), appended by ``project_work._append`` under
  ``project_work.dispatch_lock`` and admitted only at the human attestation door
  (``POST /work/observation``, ``project_work_surface``). No native operation records one: a native turn
  relabelling itself external would be an unverified claim, so the native door has no write here at all.
  These rows are not Work records (``project_work._WORK_RECORDS``): they never enter a Work's
  specification, phases, revisions, page read cut, review intent or action guards, so recording one stales
  no action basis and no review. No scheduler, heartbeat, poller or process probe lives here.

One observation shape (``qualified``)
  source (in-app | external), subject {kind, actor, session_id, turn_id}, work_id, consumed scope revision,
  observer, authority and provenance (the admitting door's attestation), observed_state, observed_at,
  expires_at, evidence (exact public {path, sha256} pins) or evidence_absent (why there is none), and the
  read-time qualification ``current`` with its ``qualification`` sentence.

States
  requested, starting, waiting, running (ACTIVE_STATES) and completed, failed, cancelled (TERMINAL_STATES);
  never merged. An external ``completed`` completes no Work and satisfies no review or integration
  obligation: it is what an observer reported about its actor.

Truth rules
  * An observation is current only while unexpired and newest (by observed_at, then ledger order) for its
    subject. After expiry the subject's current activity is UNKNOWN; the last observation stays inspectable.
    Expiry is a read-time comparison, so it changes the observer token (project_work_navigation) without a
    write.
  * Only an observation event refreshes time; nothing renews an old one. An event older than the newest
    recorded for its subject is kept as history and never becomes current (out-of-order).
  * Scope (repair1 WI-R2): an observation names the Work scope revision its actor consumed. Admission refuses a scope
    that is not the Work's current scope (CHANGED_INPUT with the exact read); after a later scope edit a recorded
    observation is HISTORICAL for the current Work (shown with both revisions), never current activity.
  * Event identity (repair1 WI-R2): an event is (subject, observed_at, observed_state). Recording the same event again
    under a new request_id is REUSED when it says exactly the same and refused when it would change its expiry, evidence or
    meaning; a tie on observed_at keeps the first recorded event. A new observed status time is a new event.
  * observed_at may lead the door's clock by at most FUTURE_SKEW_SECONDS; expires_at lies after
    observed_at and at most MAX_TTL_SECONDS after it.
  * One request_id records once; a replay with other content is refused.
  * A Work exposes at most MAX_SUBJECTS subjects (newest first) with ``subjects_total``.

Cost
  The external fold is one pass over the parsed ledger rows, cached against the identity of the owner's
  published row tuple (``project_work._fold``), so an unchanged ledger costs a dict lookup. That memo is kept only while
  the owner retains the entry (``project_work._retained``): a ledger above the owner's retention cap is folded per
  request from the caller's one capture and nothing of it stays here. An append costs
  what every Work append costs: ``project_work._append`` hashes the ledger before and after (O(ledger
  bytes)); retained storage grows by one row.
"""
from __future__ import annotations

import datetime as dt
import threading

OBSERVATION_RECORD = 'project-work-observation'
#: never 'work-order' (engine_ledger.is_work_order would list an observation as open work)
OBSERVATION_KIND = 'work-observation'
ACTIVE_STATES = ('requested', 'starting', 'waiting', 'running')
TERMINAL_STATES = ('completed', 'failed', 'cancelled')
STATES = ACTIVE_STATES + TERMINAL_STATES
FUTURE_SKEW_SECONDS = 120
MAX_TTL_SECONDS = 6 * 3600
MAX_SUBJECTS = 8
MAX_TEXT = 400
#: in-app child-host states (writing.child_hosts) to the shared state names; ORPHANED is a lost observation
IN_APP_STATES = {'STARTING': 'starting', 'WAITING': 'waiting', 'RUNNING': 'running'}

_CACHE: dict = {}          # ledger path -> (rows tuple, {project: fold})
_CACHE_LOCK = threading.Lock()


def contract() -> dict:
    """The one admission schema of ``POST /work/observation`` (the human attestation door)."""
    text = {'type': 'string', 'minLength': 1, 'maxLength': MAX_TEXT}
    evidence = {'type': 'array', 'minItems': 1, 'items': {'type': 'object', 'required': ['path', 'sha256'],
                'additionalProperties': False, 'properties': {'path': {'type': 'string'}, 'sha256': {'type': 'string'}}}}
    return {'type': 'object', 'additionalProperties': False,
            'required': ['id', 'request_id', 'subject', 'observed_state', 'observed_at', 'expires_at',
                         'consumed_scope_revision', 'observer', 'source'],
            'properties': {
                'project': {'type': 'string'}, 'id': {'type': 'string'},
                'request_id': {'type': 'string', 'pattern': '^[A-Za-z0-9._:-]{8,96}$'},
                'subject': {'type': 'object', 'additionalProperties': False, 'required': ['kind', 'actor', 'session_id'],
                            'properties': {'kind': {'enum': ['external-actor']}, 'actor': text, 'session_id': text}},
                'observed_state': {'enum': list(STATES)},
                'observed_at': {'type': 'string', 'format': 'date-time'},
                'expires_at': {'type': 'string', 'format': 'date-time'},
                'consumed_scope_revision': {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'},
                'observer': text, 'source': text, 'summary': {'type': 'string', 'maxLength': 2000},
                'evidence': evidence, 'evidence_absent': text},
            'oneOf': [{'required': ['evidence'], 'not': {'required': ['evidence_absent']}},
                      {'required': ['evidence_absent'], 'not': {'required': ['evidence']}}]}


def adapter() -> dict:
    """The exact door contract a coordinator uses with an actual actor-status result (named by every descriptor)."""
    return {'operation': 'work_observation', 'http': {'method': 'POST', 'url': '/work/observation'},
            'door': 'human attestation only; the native door has no observation write',
            'required': contract()['required'], 'one_of': ['evidence', 'evidence_absent'],
            'states': list(STATES), 'max_ttl_seconds': MAX_TTL_SECONDS, 'future_skew_seconds': FUTURE_SKEW_SECONDS,
            'says': 'Record what an actual dispatcher or actor-status read showed, with its own time and a bounded expiry. '
                    'Never a heartbeat: record only actual status events. A completed observation completes no Work.'}


def _time(value, field):
    try:
        moment = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('work_observation %s is an ISO-8601 time with a zone.' % field) from None
    if moment.tzinfo is None:
        raise ValueError('work_observation %s is an ISO-8601 time with a zone.' % field)
    return moment.astimezone(dt.timezone.utc)


def _now(now=None):
    return now.astimezone(dt.timezone.utc) if now is not None else dt.datetime.now(dt.timezone.utc)


def record(project, payload, repo_root=None, *, door=None, now=None) -> dict:
    """Admit one external execution observation at the human attestation door and append it once."""
    from jsonschema import Draft202012Validator
    from laplace.work import project_work, project_work_review
    from laplace.work.project_work_views import handle
    if (door or {}).get('origin') != 'human':
        raise ValueError('An external execution observation is attested only at the human door (POST /work/observation); '
                         'a native turn cannot assert one.')
    payload = {key: value for key, value in payload.items() if key != 'project'}
    error = next(Draft202012Validator(contract()).iter_errors(payload), None)
    if error:
        raise ValueError('work_observation does not match its owner contract: ' + error.message)
    clock = _now(now)
    observed, expires = _time(payload['observed_at'], 'observed_at'), _time(payload['expires_at'], 'expires_at')
    if (observed - clock).total_seconds() > FUTURE_SKEW_SECONDS:
        raise ValueError('observed_at is more than %d s after the door\'s clock; record the actual status time.' % FUTURE_SKEW_SECONDS)
    if not expires > observed or (expires - observed).total_seconds() > MAX_TTL_SECONDS:
        raise ValueError('expires_at lies after observed_at and at most %d s after it.' % MAX_TTL_SECONDS)
    root = project_work._root(repo_root)
    with project_work.dispatch_lock(repo_root):
        tasks = project_work._tasks(project, repo_root)
        ident = payload['id']
        if ident not in tasks:
            raise ValueError('work_observation names an existing Work id of this project.')
        scope = project_work._work_basis(tasks, ident)[0]['scope_revision']
        if payload['consumed_scope_revision'] != scope:
            raise project_work.WorkConflict('This observation names a Work scope that is not the current scope of this Work; an actor working '
                                            'on another or older scope is not current activity here. Read the Work and record the actual status '
                                            'of the scope it consumed.', project, ident, expected=payload['consumed_scope_revision'], observed=scope,
                                            field='consumed_scope_revision')
        obs_id = 'OBS-' + project_work_review._digest([project, ident, payload['request_id']])[7:31]
        row = {'record': OBSERVATION_RECORD, 'kind': OBSERVATION_KIND, 'id': obs_id, 'work_id': ident, 'project': project,
               'request_id': payload['request_id'], 'subject': dict(payload['subject']),
               'observed_state': payload['observed_state'], 'observed_at': observed.isoformat(), 'expires_at': expires.isoformat(),
               'consumed_scope_revision': payload['consumed_scope_revision'],
               'observer': payload['observer'].strip(), 'provenance': payload['source'].strip(),
               'attestation': {'door': 'human', 'by': 'author'}, 'summary': (payload.get('summary') or '').strip(),
               'evidence': project_work_review._evidence(root, payload.get('evidence')),
               **({'evidence_absent': payload['evidence_absent'].strip()} if payload.get('evidence_absent') else {}),
               'ts': clock.isoformat()}
        fold = _fold(root, project);prior = fold['by_id'].get(obs_id)
        if prior is not None and {key: prior.get(key) for key in row if key != 'ts'} != {key: value for key, value in row.items() if key != 'ts'}:
            raise ValueError('This request_id already recorded a different observation; use a new request_id.')
        if prior is None:
            # the same observed event under another request id: never a new lease or a new meaning
            same = next((other for _, other in fold['by_work'].get(ident, ()) if _event(other) == _event(row)), None)
            if same is not None and {key: same.get(key) for key in EVENT_CONTENT} != {key: row.get(key) for key in EVENT_CONTENT}:
                raise ValueError('This observed event (same subject, observed_at and state) is already recorded as %s with expiry %s; '
                                 'repeating it cannot extend or change it. Record the next actual status read with its own observed time.'
                                 % (same['id'], same.get('expires_at')))
            prior = same
        if prior is not None:
            return {'status': 'REUSED', 'observation': project_work._deep(prior),
                    'activity': work_activity(project, ident, root, now=clock),
                    'read_handle': handle(project, {'view': 'detail', 'id': ident}),
                    'owned_changes_inexact': 'nothing was written: this request or this observed event was already recorded'}
        appended = project_work._append(repo_root, row)
    return {'status': 'RECORDED', 'observation': {key: value for key, value in appended.items() if key not in {'owned_changes', 'effects'}},
            'activity': work_activity(project, ident, root, now=clock),
            'read_handle': handle(project, {'view': 'detail', 'id': ident}), 'owned_changes': appended.get('owned_changes')}


#: what one observed event says beyond its identity; a repeat must say exactly this
EVENT_CONTENT = ('expires_at', 'consumed_scope_revision', 'evidence', 'evidence_absent', 'observer', 'provenance')


def _event(row):
    subject = row.get('subject') or {}
    return (subject.get('kind'), subject.get('actor'), subject.get('session_id'), row.get('observed_at'), row.get('observed_state'))


def _fold(root, project, entry=None) -> dict:
    """External observations of one project from the owner's rows: {'by_id', 'by_work': {id: [rows]}}.

    ``entry`` is the ledger fold the caller already captured (``project_work._captured``); without one it is taken here.
    The result is memoized against the identity of that entry's row tuple only while the owner retains the entry; an
    unretained (over-cap) ledger is folded for this request alone and any memo for its path is dropped, so this cache
    never holds rows the owner declined to retain."""
    from laplace.work import project_work
    entry = project_work._fold(root) if entry is None else entry
    rows = entry['rows'];path = project_work._ledger(root)
    if not project_work._retained(root, entry):
        with _CACHE_LOCK:
            _CACHE.pop(path, None)
        return _observations(rows, project)
    with _CACHE_LOCK:
        cached = _CACHE.get(path)
        if cached is None or cached[0] is not rows:
            cached = (rows, {});_CACHE[path] = cached
            while len(_CACHE) > project_work.FOLD_CACHE_MAX_ENTRIES:
                _CACHE.pop(next(iter(_CACHE)))
        fold = cached[1].get(project)
    if fold is None:
        fold = _observations(rows, project)
        with _CACHE_LOCK:
            if _CACHE.get(path) is cached:
                cached[1][project] = fold
    return fold


def _observations(rows, project) -> dict:
    """One pass over the rows: this project's external observations by id (first recorded wins) and by Work."""
    fold = {'by_id': {}, 'by_work': {}}
    for position, row in enumerate(rows):
        if row.get('record') == OBSERVATION_RECORD and row.get('project') == project and row.get('work_id'):
            fold['by_id'].setdefault(row['id'], row)
            fold['by_work'].setdefault(row['work_id'], []).append((position, row))
    return fold


def _external(row, now, scope=None) -> dict:
    subject = row.get('subject') or {}
    return {'source': 'external', 'observation_id': row['id'], 'work_id': row['work_id'],
            'scope': {'consumed': row.get('consumed_scope_revision'), 'current': scope, 'matches': row.get('consumed_scope_revision') == scope},
            'subject': {key: subject.get(key) for key in ('kind', 'actor', 'session_id')},
            'observed_state': row.get('observed_state'), 'observed_at': row.get('observed_at'), 'expires_at': row.get('expires_at'),
            'consumed_scope_revision': row.get('consumed_scope_revision'), 'observer': row.get('observer'),
            'authority': 'attested at the human door', 'provenance': row.get('provenance'),
            'evidence': [dict(item) for item in row.get('evidence') or []], 'evidence_absent': row.get('evidence_absent')}


def _in_app(row, now) -> dict:
    state = IN_APP_STATES.get(row.get('state'))
    return {'source': 'in-app', 'work_id': row['work_id'],
            'subject': {'kind': row.get('kind'), 'session_id': row.get('session_id'), 'turn_id': row.get('turn_id'),
                        **({'dispatch_id': row['dispatch_id']} if row.get('dispatch_id') else {})},
            'observed_state': state or 'unknown', 'observed_at': now.isoformat(), 'expires_at': None,
            'observer': 'writing.turn_jobs', 'authority': 'owner-observed in this app process',
            'provenance': 'live in-process registry and child-host record; not persisted',
            'evidence': [], 'evidence_absent': 'in-app execution is observed live, not recorded as evidence',
            'current': state is not None,
            'qualification': 'In-app %s, observed now' % (state or 'execution with a lost observation (orphaned)')}


def project_activity(project, root, *, now=None, in_app=None, captured=None) -> dict:
    """Qualified activity of every Work of one project: {'by_work': {id: summary}, 'coverage', 'basis'}.

    ``captured`` is the caller's one ``project_work._captured`` pair, so the observations and the scopes that qualify
    them come from the same owner fold as the caller's records; without it one fold is captured here.

    ``basis`` is what the observer token consumes: each subject's current observation identity and state, so
    an expiry (read-time) or a new event changes it while an unrelated project's append never does."""
    from laplace.work import project_work
    from laplace.writing import turn_jobs
    clock = _now(now);root = project_work._root(root)
    live = in_app if in_app is not None else turn_jobs.work_activity(project, root)
    grouped: dict = {}
    for row in live['rows']:
        grouped.setdefault(row['work_id'], []).append(_in_app(row, clock))
    entry, tasks = captured if captured is not None else (project_work._fold(root), None)
    fold = _fold(root, project, entry)
    scopes = _current_scopes(root, project, fold['by_work'], entry, tasks)
    for work_id, rows in fold['by_work'].items():
        newest: dict = {}
        for position, row in rows:
            key = (row.get('subject') or {}).get('kind'), (row.get('subject') or {}).get('actor'), (row.get('subject') or {}).get('session_id')
            # the latest observed time wins; on a tie the FIRST recorded event stands, so a repeat never takes over
            stamp = (_time(row['observed_at'], 'observed_at'), -position)
            if key not in newest or stamp > newest[key][0]:
                newest[key] = (stamp, row)
        for (stamp, row) in sorted(newest.values(), key=lambda item: item[0], reverse=True):
            item = _external(row, clock, scopes.get(work_id))
            live_now = _time(row['expires_at'], 'expires_at') > clock
            item['current'] = live_now and item['scope']['matches']
            if not item['scope']['matches']:
                item['qualification'] = ('HISTORICAL for the current Work: external %s observed %s by %s for scope %s; the current scope is %s'
                                         % (row['observed_state'], row['observed_at'], row.get('observer'),
                                            str(row.get('consumed_scope_revision'))[:19], str(scopes.get(work_id))[:19]))
            else:
                item['qualification'] = (('External %s, observed %s by %s; expires %s' if live_now else
                                          'UNKNOWN now: last external observation (%s at %s by %s) expired %s')
                                         % (row['observed_state'], row['observed_at'], row.get('observer'), row['expires_at']))
            grouped.setdefault(work_id, []).append(item)
    by_work = {work_id: _summary(items) for work_id, items in grouped.items()}
    basis = sorted((work_id, item.get('observation_id') or item['subject'].get('turn_id') or item['subject'].get('session_id') or '',
                    item['observed_state'], item['current'], (item.get('scope') or {}).get('matches', True))
                   for work_id, items in grouped.items() for item in items)
    return {'by_work': by_work, 'basis': basis, 'observed_at': clock.isoformat(),
            'coverage': {'in_app': {'owner': 'writing.turn_jobs', 'rows': len(live['rows']), 'omitted': live['omitted'],
                                    'untargeted': live['untargeted'],
                                    'covers': 'accepted turn starts, live turns and child hosts that name a Work',
                                    'not_covered': 'research runs and turns admitted without a Work target'},
                         'external': {'owner': 'project-work-observation rows (human attestation door)',
                                      'works': len(fold['by_work']), 'rows': len(fold['by_id'])},
                         'partial': bool(live['omitted'])},
            'expires_next_at': min((item['expires_at'] for items in grouped.values() for item in items
                                    if item['current'] and item['expires_at']), default=None)}


def _current_scopes(root, project, works, entry=None, tasks=None):
    """The current scope revision of each Work that has external observations, from the same captured owner fold as the
    observations (read-only, no copies). Never a second lookup: for an unretained ledger that is a new parse with no
    project fold, which would leave every external observation unqualified."""
    from laplace.work import project_work
    if not works:
        return {}
    if tasks is None:
        tasks = project_work._captured(project, root, entry)[1]
    cache, out = {}, {}
    for ident in works:
        if ident in tasks:
            out[ident] = project_work._work_basis(tasks, ident, cache=cache)[0]['scope_revision']
    return out


def _summary(items) -> dict:
    """One Work's qualified activity: the strongest current state, else UNKNOWN when something was observed."""
    current = [item for item in items if item['current']]
    order = {state: index for index, state in enumerate(('running', 'waiting', 'starting', 'requested', 'completed', 'failed', 'cancelled'))}
    lead = min(current, key=lambda item: order.get(item['observed_state'], 99)) if current else None
    state = lead['observed_state'] if lead else 'unknown'
    subjects = items[:MAX_SUBJECTS]
    return {'state': state, 'active': state in ACTIVE_STATES, 'source': lead['source'] if lead else None,
            'qualification': lead['qualification'] if lead else items[0]['qualification'],
            'observations': subjects, 'subjects_total': len(items)}


def work_activity(project, ident, root, *, now=None, in_app=None) -> dict | None:
    """The qualified activity of one Work (None when nothing was ever observed for it)."""
    value = project_activity(project, root, now=now, in_app=in_app)
    summary = value['by_work'].get(ident)
    return None if summary is None else {**summary, 'coverage': value['coverage']}
