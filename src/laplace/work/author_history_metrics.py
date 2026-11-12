"""Metadata facets of author_history; existing rows remain the sole authority.

The index holds identities/numbers/offsets, never public prose or custody bodies.
It is disposable and advances canonical append-only journals by their suffix.
"""
from __future__ import annotations

import base64
import collections
import copy
import datetime as dt
import hashlib
import json
import math
import threading
from pathlib import Path
from urllib.parse import urlencode

SCHEMA = 'laplace.session-analytics/1'
PROJECTIONS = ('overview', 'sessions', 'trace', 'coverage', 'usage', 'delivery', 'feedback')
FILTERS = ('session_id', 'turn_id', 'work_id', 'dispatch_id', 'provider', 'model',
           'admitted_model', 'resolved_model', 'role', 'mode', 'terminal_kind',
           'operation', 'outcome', 'from', 'to')
from laplace.writing.records._index import _LOCK
from laplace.writing.records._index import _INDEXES
from laplace.writing.records._index import _KINDS
from laplace.writing.records._index import _FIELDS
from laplace.writing.records._index import _DERIVED


def contract():
    strings = {key: {'type': 'string'} for key in FILTERS}
    return {'type': 'object', 'properties': {
        **strings, 'projection': {'enum': list(PROJECTIONS)},
        'scope': {'enum': ['project', 'workspace', 'session', 'turn', 'work']},
        'cursor': {'type': 'string'}, 'as_of': {'type': 'string'},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}},
        'additionalProperties': False}


from laplace.core.identity import canonical_digest


from laplace.core.records import capture




def _time(value):
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            parsed = float(value) / (1000 if value > 10**12 else 1)
            return parsed if math.isfinite(parsed) else None
        if isinstance(value, str):
            try:
                numeric = float(value)
                parsed = numeric / (1000 if numeric > 10**12 else 1)
                return parsed if math.isfinite(parsed) else None
            except ValueError: pass
        parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=parsed.tzinfo or dt.timezone.utc).timestamp()
    except (ValueError, TypeError, OverflowError): return None


def _read_handle(project, payload):
    return {'operation': 'author_history', 'payload': payload,
            'http': {'method': 'GET', 'url': '/authoring/history?' + urlencode({'project': project, **payload})}}


def _turn_read(project, turn):
    return {'operation': 'author_history', 'payload': {'view': 'record', 'id': 'activity:journal:' + turn},
            'native_scope': 'Exact turn record; related rows are available through the turn-scoped trace.',
            'http': {'method': 'GET', 'url': '/authoring/session-turn?' + urlencode(
                {'project': project, 'id': turn, 'view': 'turn'})}}


from laplace.writing.records._index import _metadata


from laplace.writing.records._index import MetadataIndex


from laplace.writing.records._index import index


from laplace.writing.records._index import _snapshot



from laplace.writing.records._index import _dispatch_metadata_cut


def _selection(idx, project, query, upper=None, work_ids=None):
    scope = query.get('scope', 'project')
    if scope == 'workspace': candidates = idx.rows
    elif query.get('turn_id'): candidates = idx.by_turn.get(query['turn_id'], [])
    elif query.get('session_id'):
        candidates = list(idx.by_session.get(query['session_id'], []))
        candidates.extend(row for tid in idx.project_turns.get(project, ())
                          if (idx.turns.get(tid) or {}).get('session_id') == query['session_id']
                          for row in idx.by_turn.get(tid, []))
    else:
        candidates = list(idx.by_project.get(project, []))
        candidates.extend(row for sid in idx.project_sessions.get(project, ()) for row in idx.by_session.get(sid, []))
        candidates.extend(row for tid in idx.project_turns.get(project, ()) for row in idx.by_turn.get(tid, []))
    candidates = sorted({row['_order']: row for row in candidates}.values(), key=lambda row: row['_order'])
    rows = [row for row in candidates if (upper is None or row['_order'] <= upper)
            and row.get('record') not in _DERIVED
            and (scope == 'workspace' or idx.project(row) == project)]
    selected = []
    reply_filters = {}
    for row in rows:
        turn = idx.turns.get(row.get('turn_id')) or (row if row.get('record') == 'writing-turn' else {})
        session_id = row.get('session_id') or turn.get('session_id') or (row.get('id') if row['record'] == 'writing-session' else None)
        if row.get('project') and turn.get('project') and row['project'] != turn['project']:
            turn = {}
        settings = turn.get('provider_settings') or {}
        provider = settings.get('provider') or row.get('provider')
        admitted = settings.get('model')
        tid = turn.get('id')
        if query.get('resolved_model') or query.get('terminal_kind'):
            if tid not in reply_filters:
                related = [item for item in idx.by_turn.get(tid, []) if item.get('record') == 'writing-reply' and (upper is None or item['_order'] <= upper)]
                reply_filters[tid] = ({item.get('resolved_model') for item in related if item.get('resolved_model')},
                                     {item.get('status') for item in related if item.get('status')})
            resolved, terminal = reply_filters[tid]
        else: resolved, terminal = set(), set()
        if query.get('session_id') and query['session_id'] != session_id: continue
        if query.get('turn_id') and query['turn_id'] != (turn.get('id') or row.get('turn_id')): continue
        if query.get('work_id') and (turn.get('work_id') or turn.get('dispatch_id')) not in (work_ids or {query['work_id']}): continue
        if query.get('dispatch_id') and query['dispatch_id'] != turn.get('dispatch_id'): continue
        if query.get('provider') and query['provider'] != provider: continue
        if (query.get('admitted_model') or query.get('model')) and (query.get('admitted_model') or query.get('model')) != admitted: continue
        if query.get('resolved_model') and query['resolved_model'] not in resolved: continue
        if query.get('mode') and query['mode'] != turn.get('mode'): continue
        if query.get('role') and query['role'] != (idx.sessions.get(session_id) or {}).get('role'): continue
        if query.get('terminal_kind') and query['terminal_kind'] not in terminal: continue
        if query.get('operation') and query['operation'] != row.get('operation'): continue
        outcome = 'failed' if row.get('record') == 'writing-tool-failure' else row.get('outcome_status') or row.get('status')
        if query.get('outcome') and query['outcome'] != outcome: continue
        timestamp = _time(row.get('ts'))
        if query.get('from') and (timestamp is None or timestamp < _time(query['from'])): continue
        if query.get('to') and (timestamp is None or timestamp >= _time(query['to'])): continue
        selected.append(row)
    return selected


def _trace(idx, rows):
    events = []
    for row in rows:
        turn = idx.turns.get(row.get('turn_id')) or (row if row.get('record') == 'writing-turn' else {})
        project = idx.project(row)
        ident = row.get('id')
        item = {key: row.get(key) for key in _FIELDS if key in row and key not in ('request_id',)}
        item.update(event_id=ident, owner='authoring_surface', project=project,
                    logical_turn_id=turn.get('id') or row.get('turn_id'),
                    session_id=row.get('session_id') or turn.get('session_id') or (row.get('id') if row['record'] == 'writing-session' else None),
                    ledger_order=row['_order'], row_sha256=row['_hash'],
                    attribution_basis='immutable-turn-admission' if turn.get('provider_settings') else 'not-recorded',
                    duration_ms=row['duration_seconds'] * 1000 if isinstance(row.get('duration_seconds'), (int, float)) else None,
                    duration_basis='owner-recorded-tool-duration' if isinstance(row.get('duration_seconds'), (int, float)) else 'not-recorded')
        if turn.get('provider_settings') and idx.project(turn) == project: item['admitted_settings'] = turn['provider_settings']
        elif turn.get('provider_settings'): item['attribution_basis'] = 'CONFLICT-project-lineage'
        if row['record'] == 'writing-reply': item['feedback_target'] = _response_target(idx, row)
        if ident:
            item['read_handle'] = _read_handle(project, {'view': 'record', 'id': 'activity:journal:' + ident})
        if item['logical_turn_id']:
            item['turn_read'] = _turn_read(project, item['logical_turn_id'])
            item['controls_read'] = {'http':{'method':'GET','url':'/authoring/session-turn?' + urlencode(
                {'project':project,'id':item['logical_turn_id'],'view':'controls'})}}
        events.append(item)
    return events


def _original_counts(rows):
    keys = ('writing-tool-read', 'writing-tool-action', 'writing-tool-failure')
    groups = collections.defaultdict(list)
    for row in rows:
        if row['record'] in keys:
            groups[(row['record'], row.get('id'))].append(row)
    counts = {key: 0 for key in keys}
    duplicates = ambiguous = missing = 0
    for (kind, ident), occurrences in groups.items():
        if not ident:
            missing += len(occurrences); continue
        duplicates += max(0, len(occurrences) - 1)
        if len({row['_hash'] for row in occurrences}) > 1:
            ambiguous += 1; continue
        counts[kind] += 1
    return counts, {'duplicate_original_rows': duplicates,
                    'ambiguous_original_ids': ambiguous, 'missing_original_ids': missing}


def _sessions(idx, rows):
    groups = collections.defaultdict(list)
    for row in rows:
        turn = idx.turns.get(row.get('turn_id')) or (row if row.get('record') == 'writing-turn' else {})
        sid = row.get('session_id') or turn.get('session_id') or (row.get('id') if row.get('record') == 'writing-session' else None)
        if sid: groups[(idx.project(row), sid)].append(row)
    result = []
    for (owner_project, sid), events in groups.items():
        original = idx.sessions.get(sid) or {}
        turns = {row['id']: row for row in events if row.get('record') == 'writing-turn'}
        # Include turn identity metadata for a selected event window without its prompt.
        for row in events:
            turn = idx.turns.get(row.get('turn_id'))
            if turn and (idx.cut_upper is None or turn['_order'] <= idx.cut_upper):
                turns.setdefault(turn['id'], turn)
        replies = [row for row in events if row.get('record') == 'writing-reply']
        latest = replies[-1] if replies else None
        final_turn = max(turns.values(), key=lambda row: row['_order'], default={})
        counts = collections.Counter(row['record'] for row in events)
        original_counts, original_coverage = _original_counts(events)
        project = owner_project
        display = next((row.get('catalogue_display_title') for row in idx.by_session.get(sid, [])
                        if row.get('record') == 'writing-turn' and row.get('catalogue_display_title')
                        and (idx.cut_upper is None or row['_order'] <= idx.cut_upper)), None)
        result.append({'id': sid, 'session_id': sid, 'project': project,
            'title': original.get('title') or display or 'Conversation ' + sid,
            'title_basis': 'stored-title' if original.get('title') else 'existing-owner-catalogue-label' if display else 'owner-identity',
            'role': original.get('role'), 'created_at': original.get('ts'),
            'latest_recorded_at': next((row.get('ts') for row in reversed(events) if _time(row.get('ts')) is not None), None),
            'latest_ledger_order': max(row['_order'] for row in events),
            'order_basis': 'recorded activity timestamp descending, retained ledger order fallback, stable owner identity tie',
            'admitted_settings': final_turn.get('provider_settings'),
            'resolved_models': sorted({row['resolved_model'] for row in replies if row.get('resolved_model')}),
            'resolved_models_basis': 'saved owner reply field; legacy alias is not proof of actual inference model',
            'actual_model_observations': [item for row in replies for item in (row.get('usage_facts_projection') or {}).get('model_observations', [])
                                          if item.get('actual_reported_model')],
            'turn_count': len(turns), 'reply_receipt_count': len(replies),
            'distinct_replied_turns': len({row.get('turn_id') for row in replies}),
            'saved_terminal_kind': (latest or {}).get('status'),
            'latest_turn_id': final_turn.get('id'),
            'latest_admission_has_reply': any(row.get('turn_id') == final_turn.get('id') for row in replies) if final_turn else None,
            'latest_reply_target': _response_target(idx, latest) if latest else None,
            'live_state': 'UNKNOWN', 'live_basis': 'saved metadata is not a process observation',
            'work_id': final_turn.get('work_id'), 'dispatch_id': final_turn.get('dispatch_id'),
            'parent_turn_id': final_turn.get('parent_turn_id'), 'mode': final_turn.get('mode'),
            'original_tool_attempts': original_counts,
            'tool_identity_coverage': original_coverage,
            'retained_failure_receipts': counts['writing-tool-failure'],
            'artifact_receipt_count': counts['writing-artifact'],
            'application_receipt_count': counts['writing-application'],
            'usage_coverage': {'reply_receipts': len(replies),
                'legacy_reported': sum('legacy_usage' in row for row in replies),
                'collector_projection_headers': sum('usage_facts_projection' in row for row in replies),
                'missing_is_zero': False},
            'read_handle': {'http': {'method': 'GET', 'url': '/authoring/session?' + urlencode(
                {'project': project, 'id': sid, 'view': 'summary', 'limit': 20})}},
            'activity_read': _read_handle(project, {'view': 'telemetry', 'projection': 'trace',
                                                   'scope': 'session', 'session_id': sid})})
    return sorted(result, key=lambda row: (_time(row['latest_recorded_at']) or 0, row['latest_ledger_order'], row['id']), reverse=True)


from laplace.writing.records._index import _provider_header


def _response_target(idx, row):
    from laplace.work.feedback import TARGET_SCHEMA
    turn = idx.turns.get(row.get('turn_id')) or {}; sid = turn.get('session_id')
    project = idx.project(row)
    if len(idx.by_id.get(row.get('id'), [])) != 1: return None
    if not (row.get('id') and sid and row.get('response_sha256') and project and idx.project(turn) == project): return None
    return {'schema_version': TARGET_SCHEMA, 'kind': 'response', 'project': project,
            'session_id': sid, 'turn_id': turn['id'], 'reply_record_id': row['id'], 'response_sha256': row['response_sha256']}


def _admission_handle(project, tid):
    return _read_handle(project, {'view': 'record', 'id': 'activity:admission:' + tid})


def _usage_items(idx, rows):
    result = []; groups = collections.defaultdict(list)
    for row in rows:
        if row['record'] != 'writing-reply': continue
        header = row.get('usage_facts_projection') or {}
        identity = header.get('attempt_id') or row.get('id') or 'unidentified:' + str(row['_order'])
        groups[(idx.project(row), identity)].append(row)
    for (owner_project, attempt), replies in groups.items():
        row = replies[-1]; header = row.get('usage_facts_projection'); project = idx.project(row)
        turn = idx.turns.get(row.get('turn_id')) or {}
        ambiguous = len({canonical_digest(item.get('usage_facts_projection')) for item in replies}) > 1
        valid = isinstance(header, dict) and header.get('status') != 'UNAVAILABLE' and not ambiguous
        if valid and header.get('logical_turn_id') not in (None, row.get('turn_id')): valid = False
        item = {'attempt_id': attempt if valid else None, 'project':project, 'turn_id':row.get('turn_id'),
                'session_id': turn.get('session_id') or row.get('session_id'), 'ts':row.get('ts'),
                'reply_record_ids':sorted({item.get('id') for item in replies if item.get('id')}),
                'terminal_kind': row.get('status'), 'terminal_status_variants': sorted({item['status'] for item in replies if item.get('status')}), 'admitted_settings':turn.get('provider_settings'),
                'resolved_model':row.get('resolved_model'),
                'resolved_model_basis':'saved owner reply field; actual model requires explicit model observation',
                'reported_actual_models':sorted({item['actual_reported_model'] for item in (header or {}).get('model_observations',[]) if item.get('actual_reported_model')}) if valid else [],
                'duplicate_reply_receipts':len(replies)-1,
                'status': 'RECORDED' if valid else 'UNAVAILABLE' if header or row.get('usage_facts_reference') else 'LEGACY_UNKNOWN',
                'selected': header.get('selected') if valid else None,
                'baseline':header.get('baseline') if valid else None, 'reset_epoch':header.get('reset_epoch') if valid else None,
                'model_observations':header.get('model_observations',[]) if valid else [],
                'coverage':header.get('coverage') if valid else {'reason':'conflicting-attempt-headers' if ambiguous else 'unknown-or-missing-owner-basis'},
                'legacy_report': {'counts':row.get('legacy_usage'), 'basis':'unknown; never summed as logical-turn spend'} if row.get('legacy_usage') else None,
                'legacy_context_proxy': {'value':row.get('context_tokens_used'), 'basis':'legacy response field; not consumption'} if 'context_tokens_used' in row else None,
                'exact_turn_read':_turn_read(project,row.get('turn_id')) if row.get('turn_id') else None}
        result.append(item)
    return sorted(result, key=lambda row: (_time(row.get('ts')) or 0, str(row['turn_id'])), reverse=True)


def _usage_totals(items):
    from laplace.writing import operating as owner
    bins = collections.defaultdict(list); unknown = 0
    for item in items:
        selected = (item.get('selected') or {}).get('logical_turn')
        if not selected or selected.get('counter_domain') not in owner.USAGE_FACTS_CONTRACT['counter_domains'] or selected.get('counter_scope') != 'logical_turn' or selected.get('completeness') != 'complete_for_reported_scope':
            unknown += 1; continue
        actual_models = item.get('reported_actual_models') or []
        actual_model = actual_models[0] if len(actual_models) == 1 else None
        bins[(item.get('admitted_settings') or {}).get('provider'), actual_model, selected.get('basis'), selected.get('counter_domain')].append(selected)
    summaries = []
    for (provider, model, basis, domain), selected in bins.items():
        counts = {}; coverage = {}
        for key in owner.USAGE_FACTS_CONTRACT['counts']:
            values = [(item.get('counts') or {}).get(key) for item in selected]
            coverage[key] = {'reported':sum(value is not None for value in values),'unknown':sum(value is None for value in values)}
            counts[key] = sum(values) if all(value is not None for value in values) else None
        summaries.append({'provider':provider,'actual_reported_model':model, 'model_basis':'explicit provider model observation' if model else 'UNAVAILABLE-or-multiple-models', 'basis':basis,'counter_domain':domain,
                          'unique_attempts':len(selected),'reported_counts':counts,'coverage':coverage})
    return {'by_compatible_reported_basis':summaries,'unknown_logical_turn_attempts':unknown,
            'unique_saved_attempt_groups':len(items), 'billed_cost':None,'billed_cost_basis':'not recorded; subscription sessions are not invoiced per turn',
            'cost_estimate_total':None,'cost_estimate_basis':'reported variants remain per-observation, their domains are not assumed additive',
            'context_snapshots_are_summed':False,'reasoning_is_subset_of_output':owner.USAGE_FACTS_CONTRACT['reasoning_is_subset_of_output']}


def _delivery_items(idx, rows):
    result = []
    for row in rows:
        if row['record'] != 'writing-reply': continue
        project = idx.project(row); turn = idx.turns.get(row.get('turn_id')) or {}
        header = row.get('delivery_receipt_projection') or {}
        result.append({'reply_record_id':row.get('id'),'turn_id':row.get('turn_id'),'session_id':turn.get('session_id'),
            'project':project,'status':'RECORDED' if header and header.get('status') != 'UNAVAILABLE' else 'UNAVAILABLE',
            'receipt':header or None, 'context_id':turn.get('context_id'),
            'tool_contract_digest':turn.get('tool_contract_digest'), 'science_context_digest':turn.get('science_context_digest'),
            'admission_read':_admission_handle(project,turn['id']) if turn.get('id') else None,
            'exact_turn_read':_turn_read(project,turn['id']) if turn.get('id') else None,
            'coverage':'Actual delivered channels only where owner receipt records their state; admission is retained separately.'})
    return result


def _feedback_metadata(row, offset, end, order, line_hash):
    if row.get('record')=='feedback-origin-settlement':return None
    if not isinstance(row.get('id'), str): return None
    value = {key: row.get(key) for key in ('id', 'project', 'ts', 'status', 'by', 'record', 'kind',
             're', 'supersedes', 'node_id', 'scope', 'file') if isinstance(row.get(key), str)}
    anchor = row.get('anchor') or {}
    if isinstance(anchor, dict):
        value['anchor'] = {key: anchor.get(key) for key in ('file', 'section', 'section_id', 'paragraph_id', 'node_id',
            'proposal_version', 'candidate_version', 'edit_id', 'application_id', 'source_sha256',
            'version_id', 'correction_id', 'context_role', 'feedback_effect') if isinstance(anchor.get(key), str)}
        if isinstance(anchor.get('spec_ids'), list): value['anchor']['spec_ids']=[item for item in anchor['spec_ids'] if isinstance(item,str)]
        for key in ('line_start','line_end'):
            if type(anchor.get(key)) is int: value['anchor'][key]=anchor[key]
        if isinstance(anchor.get('feedback_target'), dict):
            from laplace.work.feedback import TARGET_FIELDS
            value['anchor']['feedback_target'] = {key: anchor['feedback_target'].get(key) for key in TARGET_FIELDS}
    history = row.get('status_history')
    if isinstance(history, list): value['status_history'] = [{key: item.get(key) for key in ('status', 'at', 'by')
        if isinstance(item.get(key), str)} for item in history if isinstance(item, dict)]
    value.update(record=value.get('record') or value.get('kind') or 'note',
                 _offset=offset, _end=end, _order=order, _hash=line_hash)
    return value


def _feedback_sources(root, project):
    from laplace.pipeline import authoring
    try:
        state_path, source = authoring._state_path(project, root)
    except ValueError: return []
    homes = {state_path.parent}
    if source.get('manuscript_dir'):
        home = (Path(root) / source['manuscript_dir']).resolve()
        if home.is_relative_to(Path(root).resolve()): homes.add(home)
    return [index(root, home / 'feedback/feedback.jsonl', _feedback_metadata) for home in sorted(homes)]


def _feedback_items(project, query, root, eligible_turns=None):
    from laplace.work.feedback import validate_target
    selected = []
    for source in _feedback_sources(root, project):
        for row in source.rows:
            if row.get('project') not in (None, project): continue
            anchor = row.get('anchor') or {}; target = anchor.get('feedback_target')
            basis = 'unlinked-legacy-feedback'; match = False
            if target:
                try: validate_target(project, target, root); basis = 'validated-exact-response'; match = True
                except ValueError: basis = 'UNAVAILABLE-target-unresolved-or-unsupported'
            if query.get('session_id') and (not match or target.get('session_id') != query['session_id']): continue
            if query.get('turn_id') and (not match or target.get('turn_id') != query['turn_id']): continue
            attribution_filters = ('work_id','dispatch_id','provider','model','admitted_model','resolved_model','role','mode','terminal_kind')
            if any(query.get(key) for key in attribution_filters):
                if not match or target.get('turn_id') not in (eligible_turns or set()): continue
            if query.get('outcome') and query['outcome'] != row.get('status'): continue
            if query.get('operation') and query['operation'] != 'note': continue
            if query.get('from') and (_time(row.get('ts')) is None or _time(row['ts']) < _time(query['from'])): continue
            if query.get('to') and (_time(row.get('ts')) is None or _time(row['ts']) >= _time(query['to'])): continue
            activity_id = 'activity:feedback:' + row['id']
            selected.append({'id': row['id'], 'project': project, 'owner': 'manuscript_bridge',
                'record_kind': row['record'], 'status': row.get('status'), 'actor_recorded': row.get('by'),
                'ts': row.get('ts'), 'feedback_target': target, 'target_basis': basis,
                'feedback_effect': anchor.get('feedback_effect') or 'legacy-owner-semantics',
                'status_history': row.get('status_history', []), 'reply_to': row.get('re'),
                'supersedes': row.get('supersedes'), 'lineage': anchor,
                'read_handle': _read_handle(project, {'view': 'record', 'id': activity_id}),
                'row_sha256': row['_hash'], '_source': str(source.path), '_order': row['_order']})
    return sorted(selected, key=lambda row: (_time(row.get('ts')) or 0, row['id']), reverse=True)


def exact_feedback(project, ident, root):
    raw_id = ident.removeprefix('activity:feedback:'); found = []
    with _LOCK:
        for source in _feedback_sources(root, project):
            found.extend((source, row) for row in source.by_id.get(raw_id, []) if row.get('project') in (None, project))
        if len(found) != 1: raise ValueError('Feedback ID is missing or ambiguous in selected project.')
        source, row = found[0]
        with source.path.open('rb') as stream:
            stream.seek(row['_offset']); raw = stream.read(row['_end'] - row['_offset'])
        if 'sha256:' + hashlib.sha256(raw).hexdigest() != row['_hash']:
            raise ValueError('Exact feedback changed; refresh the owner cut.')
        return json.loads(raw)


def _work_metadata(row, offset, end, order, line_hash):
    if row.get('record') not in {'project-work', 'project-work-transition'}: return None
    value = {key: row.get(key) for key in ('id', 'task_id', 'project', 'record', 'ts',
             'parent_work_id', 'status', 'obligation_id') if key in row}
    for key in ('logical_target', 'source_ref'):
        if isinstance(row.get(key), dict):
            value[key] = {k: v for k, v in row[key].items() if k in
                          ('id', 'node_id', 'kind', 'owner', 'file', 'path', 'sha256', 'revision')}
        elif isinstance(row.get(key), str): value[key] = row[key]
    if isinstance(row.get('depends_on'), list): value['depends_on'] = list(row['depends_on'])
    value.update(_offset=offset, _end=end, _order=order, _hash=line_hash)
    return value


def _work_scope(root, project, query):
    source = index(root, 'corpus_friction/work_orders.jsonl', _work_metadata)
    rows = [row for row in source.rows if query.get('scope') == 'workspace' or row.get('project') == project]
    tasks = {}
    for row in rows:
        ident = row.get('task_id') or row.get('id')
        if ident: tasks[(row.get('project'), ident)] = {**tasks.get((row.get('project'), ident), {}), **row, 'id': ident}
    selected = query.get('work_id'); included = {selected} if selected else set()
    issues = []
    if selected:
        if (project, selected) not in tasks: issues.append('Selected work has no retained owner record.')
        changed = True
        while changed:
            changed = False
            for (owner, ident), row in tasks.items():
                if owner == project and row.get('parent_work_id') in included and ident not in included:
                    included.add(ident); changed = True
        for ident in included:
            seen = set(); cursor = ident
            while cursor:
                if cursor in seen: issues.append('Containment cycle at ' + cursor); break
                seen.add(cursor); node = tasks.get((project, cursor))
                if not node: issues.append('Missing containing work: ' + cursor); break
                cursor = node.get('parent_work_id')
    relevant = [row for row in rows if not selected or (row.get('task_id') or row.get('id')) in included]
    return tasks, {'basis': 'existing project-work parent_work_id; prerequisites are not containment',
        'included_work_ids': sorted(included), 'issues': sorted(set(issues)),
        'revision': canonical_digest([(row.get('id'), row['_hash']) for row in relevant])}


def _nesting(idx, rows, tasks):
    turns = {}
    for row in rows:
        turn = idx.turns.get(row.get('turn_id')) or (row if row['record'] == 'writing-turn' else {})
        if turn.get('id'): turns[turn['id']] = turn
    children = collections.defaultdict(list)
    for tid, turn in turns.items():
        if turn.get('parent_turn_id'): children[turn['parent_turn_id']].append(tid)
    events = collections.defaultdict(list)
    for row in rows:
        tid = row.get('turn_id') or (row.get('id') if row['record'] == 'writing-turn' else None)
        if tid: events[tid].append(row)
    leafs = []
    for tid, turn in turns.items():
        counts, coverage = _original_counts(events[tid]); project = idx.project(turn)
        wid = turn.get('work_id') or turn.get('dispatch_id'); task = tasks.get((project, wid)) or {}
        leafs.append({'turn_id': tid, 'session_id': turn.get('session_id'), 'project': project,
            'parent_turn_id': turn.get('parent_turn_id'), 'child_turn_ids': sorted(children.get(tid, [])),
            'work_id': wid, 'queued_work_ids': turn.get('queued_work_ids', []),
            'allocation': 'explicit-work-association' if wid else 'unallocated-shared-turn',
            'owner_ref': {'owner': 'authoring_surface', 'kind': 'writing-turn', 'id': tid, 'project': project},
            'conceptric_mapping': {'logical_target': task.get('logical_target'), 'obligation_id': task.get('obligation_id'),
                                  'status': 'owner-declared' if task.get('logical_target') or task.get('obligation_id') else 'unmapped'},
            'original_tool_attempts': counts, 'coverage': coverage,
            'failure_receipts': sum(row['record'] == 'writing-tool-failure' for row in events[tid]),
            'saved_terminal_kinds': sorted({row['status'] for row in events[tid] if row['record'] == 'writing-reply' and row.get('status')}),
            'execution_coverage': 'saved-terminal-receipt' if any(row['record']=='writing-reply' for row in events[tid]) else 'UNKNOWN'})
    return {'basis': 'Unique turn leaves; parent_turn_id and work containment remain separate. No child sums are added to global leaves.',
            'turns': leafs, 'unallocated_turn_ids': [row['turn_id'] for row in leafs if row['allocation'] == 'unallocated-shared-turn']}


def read(project, query, root):
    with _LOCK:
        return _read_locked(project, query, root)


def _read_locked(project, query, root):
    query = {key: value for key, value in query.items() if key not in ('view', 'project')}
    unknown = set(query) - set(contract()['properties'])
    if unknown: raise ValueError('Unknown analytics query fields: ' + ', '.join(sorted(unknown)))
    for key, value in query.items():
        if key != 'limit' and not isinstance(value, str):
            raise ValueError('Analytics ' + key + ' must be a declared string, not an omitted filter.')
    projection = query.get('projection', 'overview'); scope = query.get('scope', 'project')
    if projection not in PROJECTIONS or scope not in ('project', 'workspace', 'session', 'turn', 'work'):
        raise ValueError('Unknown analytics projection or scope.')
    if scope != 'workspace' and not project: raise ValueError('Select an exact project for this analytics scope.')
    for name in ('session', 'turn', 'work'):
        if scope == name and not query.get(name + '_id'): raise ValueError('This scope requires ' + name + '_id.')
    for key in ('from', 'to'):
        if query.get(key) and _time(query[key]) is None: raise ValueError(key + ' must be an ISO or epoch timestamp.')
    if query.get('from') and query.get('to') and _time(query['from']) >= _time(query['to']):
        raise ValueError('from must precede to.')
    raw_limit = query.get('limit', 50)
    if isinstance(raw_limit, bool) or not str(raw_limit).isdigit(): raise ValueError('Analytics limit must be an integer.')
    limit = int(raw_limit)
    if not 1 <= limit <= 100: raise ValueError('Analytics limit must be 1..100.')
    identity_query = {key: value for key, value in query.items() if key not in ('cursor', 'as_of', 'limit')}
    identity_query.update(projection=projection, scope=scope)
    identity = canonical_digest({'project': project if scope != 'workspace' else None, 'query': identity_query})
    cursor = capture.decode_cut(query['cursor']) if query.get('cursor') else None
    previous = capture.decode_cut(query['as_of']) if query.get('as_of') else cursor
    for supplied in (cursor, previous):
        if supplied and supplied.get('query') != identity:
            raise ValueError('Analytics cursor/cut belongs to another scope/filter.')
    if cursor and previous and any(cursor.get(key) != previous.get(key) for key in ('query','upper','revision')):
        raise ValueError('Analytics cursor and as_of must describe the same owner cut.')
    idx = index(root)
    work, work_scope = _work_scope(root, project, query)
    upper = previous.get('upper') if previous else None
    idx = _snapshot(idx, upper)
    row_query = {key: val for key, val in identity_query.items() if projection != 'feedback' or key not in ('from','to','operation','outcome')}
    rows = _selection(idx, project, row_query, upper, set(work_scope['included_work_ids']))
    upper = max((row['_order'] for row in rows), default=0) if upper is None else upper
    feedback = []
    if projection == 'feedback':
        if scope == 'workspace':
            from laplace.pipeline import registry
            projects = set(registry.all_projects(root)) | {idx.project(row) for row in rows if idx.project(row)}
        else: projects = {project}
        feedback = [row for owner_project in sorted(projects) for row in _feedback_items(owner_project, identity_query, root,
            {row.get('turn_id') or row.get('id') for row in rows if row.get('turn_id') or row['record']=='writing-turn'})]
    revision = canonical_digest({'feedback': [(row['id'], row['row_sha256']) for row in feedback], 'talk': [(row.get('id'), row['_hash']) for row in rows], 'work': work_scope['revision']})
    if previous and previous.get('revision') != revision:
        raise ValueError('Selected analytics history changed; read a fresh owner cut. No pages were mixed.')
    cut = {'v': 1, 'query': identity, 'upper': upper, 'revision': revision}
    token = capture.encode_cut(cut)
    coverage = {'selected_metadata_rows': len(rows),
        'original_tool_attempts': sum(_original_counts(rows)[0].values()),
        **_original_counts(rows)[1],
        'unjoined_turn_rows': sum(bool(row.get('turn_id')) and row['turn_id'] not in idx.turns for row in rows),
        'talk_source_status': idx.source_status, 'malformed_source_rows_unattributed': idx.malformed_rows,
        'usage_basis': 'legacy numeric reports do not establish complete logical-turn consumption',
        'body_reads': 0, 'raw_content_in_aggregates': False,
        'identity_issues': [issue for issue in idx.identity_issues if scope == 'workspace' or issue['id'] in
                            {value for row in rows for value in (row.get('id'), row.get('turn_id'), row.get('session_id'))}]}
    if projection == 'sessions': items = _sessions(idx, rows)
    elif projection == 'trace': items = _trace(idx, rows)
    elif projection == 'usage': items = _usage_items(idx, rows)
    elif projection == 'delivery': items = _delivery_items(idx, rows)
    elif projection == 'feedback': items = [{key: val for key, val in row.items() if not key.startswith('_')} for row in feedback]
    else: items = []
    offset = int((cursor or {}).get('offset', 0))
    page = items[offset:offset + limit]
    next_read = None
    if offset + len(page) < len(items):
        next_token = capture.encode_cut({**cut, 'offset': offset + len(page)})
        next_read = _read_handle(project, {'view': 'telemetry', **identity_query,
                                          'limit': limit, 'cursor': next_token})
    envelope = {'schema_version': SCHEMA, 'project': project if scope != 'workspace' else None,
        'projection': projection, 'scope': scope, 'filters': identity_query,
        'as_of': token, 'read_cut': {'revision': revision, 'scope': 'selected metadata rows through retained owner cut'},
        'coverage': coverage, 'work_scope': work_scope, 'items': page,
        'pagination': {'total': len(items), 'offset': offset, 'limit': limit, 'next_read': next_read},
        'limits': ['Saved metadata is not live execution or scientific acceptance.',
                   'Legacy usage is unknown counter basis, not zero or a cost total.',
                   'Full source/response/error/comment bodies remain behind exact owner reads.']}
    if projection in ('overview', 'coverage'):
        envelope['totals'] = {'sessions': len(_sessions(idx, rows)),
            'logical_turns': len({row['id'] for row in rows if row['record'] == 'writing-turn'}),
            'original_tool_attempts': coverage['original_tool_attempts'],
            'retained_tool_failures': sum(row['record'] == 'writing-tool-failure' for row in rows)}
        envelope['nesting'] = _nesting(idx, rows, work)
    if idx.source_status != 'AVAILABLE' or idx.malformed_rows:
        envelope['status'] = 'PARTIAL'
        envelope['reason'] = 'Canonical journal is missing or contains unclassified malformed rows; absence is not complete coverage.'
    if projection == 'usage': envelope['accounting'] = _usage_totals(items)
    if projection == 'delivery': envelope['delivery_coverage'] = {'reply_receipts': len(items), 'recorded_headers': sum(item['status'] == 'RECORDED' for item in items), 'missing_is_zero': False}
    if projection == 'feedback':
        envelope['feedback_coverage'] = {'recorded_feedback':len(items),
            'validated_response_targets':sum(row['target_basis']=='validated-exact-response' for row in items),
            'unlinked_or_unresolved':sum(row['target_basis']!='validated-exact-response' for row in items),
            'basis':'Existing registered project ledgers; no sentiment or timestamp attribution, absent linkage stays unknown.'}
    return copy.deepcopy(envelope)


from laplace.writing.records._index import exact_record



from laplace.writing.records._index import _invalidate_index_cut


from laplace.writing.records._index import _raw_indexed_record


from laplace.writing.records._index import _exact_record_locked


from laplace.writing.records._index import artifact_record
