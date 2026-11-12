"""THE SESSION READ MODEL: the native session view and the /authoring session and session-turn reads, over the
journal records. Moved unchanged out of laplace.web.authoring, which keeps only the /authoring HTTP door.

  session_state(root, session_id, ...)              the session page (full or summary), its live turn and controls
  session_turn_detail(root, project, turn_id, ...)  one turn: summary, controls, actions, proposals, failures
  pending_proposals(root, project, ...)             the proposal navigation read for a project or one turn
  artifact_record(root, project, artifact_id)       bounded metadata for one project-scoped artifact receipt
  _turn_failure_rows / _turn_failure_view           a turn's failures and their recovery reads (_failure_*)
  _artifact_result_links / _application_receipt_*   the links and receipts a turn view carries

The passive shapes are laplace.writing.session_projection's; the journal index and fold are laplace.writing.records';
the live turn registry is laplace.writing.turn_jobs'; child execution and the steering mailbox are
laplace.writing.child_hosts'. This module holds no state, lock or cache of its own.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from laplace.core import admission
from laplace.projects import artifacts
from laplace.writing import session_projection
from laplace.writing.records._fold import _LOCK, _canonical_read_payload, _records
from laplace.writing.session_projection import editor_actions as _editor_actions
from laplace.manuscript.source_effects import applications as _applications, applied_edits as _applied_edits
from laplace.manuscript.proposal_currentness import proposal_view
from laplace.writing.provider import context_window_advertised


class MessagePartRefusal(ValueError):
    """A pinned public message changed; no replacement content was delivered."""
    def __init__(self, payload, expected, current):
        super().__init__('The selected public message changed; explicitly restart its read.')
        self.details={'message_refusal':{'code':'CHANGED_MESSAGE',
            **{key:payload[key] for key in ('project','session_id','turn_id','part')},
            'expected_basis':expected,'current_basis':current,
            'restart_read':_message_handle(payload,offset=0)}}


def message_refusal_details(error):
    return error.details if isinstance(error,MessagePartRefusal) else {}


def _message_handle(payload, *, offset, basis=None):
    from urllib.parse import urlencode
    identity={key:payload[key] for key in ('project','session_id','turn_id','part')}
    request={**identity,'offset':offset,'limit':payload['limit'],
             **({'expected_basis':basis} if basis else {})}
    native={key:value for key,value in request.items() if key!='project'}
    return {'identity':identity,
        'http':{'method':'GET','url':'/authoring/session-turn?'+urlencode({
            **{key:value for key,value in request.items() if key!='turn_id'},'id':request['turn_id'],'view':'message'})},
        'native':{'operation':'conversation_history','payload':{'view':'message',**native}},
        'sdk':{'method':'conversation_message','payload':request}}


def _message_value(root, value):
    """Decode only this selected leaf/outer wrapper, never its nested edit/context refs."""
    import json
    from laplace.core import bodies
    from laplace.representation import writing_bodies
    seen=set()
    while bodies.is_reference(value):
        key=(value.get('store'),value.get('content_handle'))
        if key in seen:raise ValueError('Selected public-message body has a reference cycle.')
        seen.add(key)
        value=json.loads(writing_bodies.read_bytes(value,root))
    return value


class _MessageFields(Mapping):
    """Lazy closed presentation fields, so precedence never opens an unused body."""
    def __init__(self,root,value,keys,paths,prefix=''):
        self.root=root;self.value=value;self.keys=keys;self.paths=paths;self.prefix=prefix;self.cache={}
    def __iter__(self):return (key for key in self.keys if key in self.value)
    def __len__(self):return sum(key in self.value for key in self.keys)
    def __getitem__(self,key):
        if key not in self.keys or key not in self.value:raise KeyError(key)
        if key not in self.cache:
            self.paths.append(self.prefix+key)
            value=_message_value(self.root,self.value[key])
            if key=='proposal' and isinstance(value,Mapping):
                value=_MessageFields(self.root,value,('answer',),self.paths,'proposal.')
            self.cache[key]=value
        return self.cache[key]


def public_message(root:Path, payload:dict) -> dict:
    """One selected request/displayed reply at a verified journal cut; no rich fold."""
    from laplace.core import identity
    from laplace.writing import records
    from urllib.parse import urlencode
    allowed={'project','session_id','turn_id','part','offset','limit','expected_basis'}
    required={'project','session_id','turn_id','part'}
    if not isinstance(payload,dict) or set(payload)-allowed or required-set(payload):
        raise ValueError('Select one closed project/session/turn public-message part.')
    if any(not isinstance(payload[key],str) or not 1<=len(payload[key])<=160
           for key in ('project','session_id','turn_id')) or payload['part'] not in ('request','reply'):
        raise ValueError('Select exact project/session/turn identities and request or reply.')
    offset=payload.get('offset',0)
    limit=payload.get('limit',2000 if payload['part']=='request' else 4000)
    if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=40000:
        raise ValueError('Message pages use non-negative character offsets and a 1-40000 character limit.')
    expected=payload.get('expected_basis')
    if 'expected_basis' in payload and (not isinstance(expected,str) or not re.fullmatch(r'sha256:[0-9a-f]{64}',expected)):
        raise ValueError('Message basis must be an owner-issued SHA-256 seal.')
    payload={**payload,'offset':offset,'limit':limit}
    root=Path(root).resolve();project=payload['project'];sid=payload['session_id'];tid=payload['turn_id']
    from laplace.writing.records import _index as owner_index
    with records.index_lock:
        idx=records.index(root)
        def selected(ident,kind,**pin):
            # THE canonical record-family resolution (B owner, records._index): legitimate writing-session versions
            # resolve; immutable duplicates, kind/project collisions and contradictory session histories refuse.
            try:resolved=owner_index.resolve_record_family(idx,project,ident,kind=kind,**pin)
            except owner_index.AmbiguousRecord as error:
                raise ValueError('The selected public-message identity is missing, ambiguous or foreign.') from error
            # An immutable public identity keeps this reader's original fence: one journal row in every project.
            if resolved is None or kind!=owner_index.SESSION_FAMILY and len(idx.by_id.get(ident,()))!=1:
                raise ValueError('The selected public-message identity is missing, ambiguous or foreign.')
            return resolved['meta'],resolved['raw']
        _current,session=selected(sid,'writing-session')
        # The saved message seals the session's immutable membership through its first recorded version, selected
        # explicitly as retained history. Later settings versions are data for future turns, not this message's
        # evidence; a contradicting identity has already refused in the current family resolution above.
        origin=min((row for row in idx.by_id.get(sid,()) if idx.project(row)==project),key=lambda row:row['_order'])
        session_meta,_origin=selected(sid,'writing-session',retained_row_sha256=origin['_hash'])
        turn_meta,turn=selected(tid,'writing-turn')
        if session.get('project')!=project or turn.get('session_id')!=sid or turn.get('project') not in (None,'',project):
            raise ValueError('The selected public message does not belong to this project conversation.')
        source_meta,source=turn_meta,turn
        if payload['part']=='reply':
            replies=[row for row in idx.by_turn.get(tid,()) if row['record']=='writing-reply']
            if len(replies)>1:raise ValueError('The selected public reply is ambiguous.')
            if replies:
                source_meta,source=selected(replies[0]['id'],'writing-reply')
                if (source.get('turn_id')!=tid or source.get('session_id') not in (None,'',sid)
                        or source.get('project') not in (None,'',project)):
                    raise ValueError('The selected public reply belongs to another conversation.')
            else:source=None
    target={key:payload[key] for key in ('project','session_id','turn_id','part')}
    common={'schema_version':'laplace.writing-message-part/1',**target,
        'restart_read':_message_handle(payload,offset=0),
        'audit_read':{'http':{'method':'GET','url':'/authoring/session-turn?'+urlencode({
            'project':project,'id':tid,'view':'turn'})}}}
    if source is None:
        if expected:raise MessagePartRefusal(payload,expected,None)
        return {**common,'state':'ABSENT','reason':'NO_SAVED_REPLY','basis':None,'content':None,
                'currentness':{'state':'ABSENT_AT_READ'},'page_read':None,'next_read':None}
    paths=[]
    if payload['part']=='request':
        if 'text' not in source:raise ValueError('The selected saved request text is unavailable.')
        text=_message_value(root,source['text']);origin='text';paths.append('text')
        if not isinstance(text,str):raise ValueError('The selected saved request is not public text.')
    else:
        presentation=session_projection.reply_presentation(_MessageFields(root,source,
            ('display_text','proposal','text','error'),paths))
        text=presentation['text'];origin=presentation['origin']
    try:raw=text.encode('utf-8')
    except UnicodeEncodeError:raise ValueError('The saved public message is not valid UTF-8 text.') from None
    row_pin=lambda meta:'sha256:'+meta['_hash'].removeprefix('sha256:')
    source_basis={'source_record_id':source_meta['id'],'source_row_sha256':row_pin(source_meta),
        'session_row_sha256':row_pin(session_meta),'turn_row_sha256':row_pin(turn_meta),
        'presentation_policy':session_projection.PUBLIC_MESSAGE_PRESENTATION,
        'presentation_origin':origin,'content_sha256':identity.bytes_digest(raw)}
    basis=identity.canonical_digest({**target,**source_basis})
    if expected and expected!=basis:raise MessagePartRefusal(payload,expected,basis)
    if offset>len(text):raise ValueError('Message offset is beyond the complete selected text.')
    end=min(len(text),offset+limit);content=text[offset:end];complete=offset==0 and end==len(text)
    return {**common,**source_basis,'state':'AVAILABLE','basis':basis,'content':content,
        'offset':offset,'end':end,'limit':limit,'total_characters':len(text),'total_utf8_bytes':len(raw),
        'page_utf8_bytes':len(content.encode('utf-8')),'units':'Unicode scalar-value characters',
        'complete':complete,'truncated':not complete,'currentness':{'state':'CURRENT_AT_READ','basis':basis},
        'presentation_dependencies':paths,'page_read':_message_handle(payload,offset=offset,basis=basis),
        'next_read':_message_handle(payload,offset=end,basis=basis) if end<len(text) else None}


# ---- moved from laplace.web.authoring (2026-10-21, core native/physical closure)
def turn_request(root: Path, project: str, session_id: str, request_id: str) -> dict:
    """Pure reconciliation of one selected-action parent submission, never a retry."""
    from laplace.writing import records
    from urllib.parse import urlencode
    if not all(isinstance(value, str) and 1 <= len(value) <= 160 for value in (project, session_id, request_id)):
        raise ValueError('An exact project, original session and parent request are required.')
    saved = records.fold_records(Path(root))
    session = saved['sessions'].get(session_id)
    if not session or session.get('project') != project or session.get('role', 'author') != 'author' or session.get('dispatch_id'):
        raise ValueError('Unknown original author session in this project.')
    matches = [row for row in saved['turns'].values() if row.get('project') == project and row.get('request_id') == request_id]
    if len(matches) > 1:
        raise ValueError('Parent submission request is ambiguous.')
    receipt = None
    if matches:
        turn = matches[0]
        if turn.get('session_id') != session_id or not turn.get('action_submission_intent_sha256'):
            raise ValueError('Request does not name this session selected-action submission.')
        receipt = {'turn_id': turn['id'], 'session_id': session_id, 'request_id': request_id,
                   'intent_sha256': turn['action_submission_intent_sha256'],
                   'read': {'http': {'method': 'GET', 'url': '/authoring/session-turn?' + urlencode({
                       'project': project, 'id': turn['id'], 'view': 'turn'})}}}
    return {'project': project, 'session_id': session_id, 'request_id': request_id,
            'effect': 'RECORDED' if receipt else 'NONE', 'receipt': receipt, 'exact': True}


def reader_request(root, project, request_id, manifest_id):
    """Pure fresh-Start reconciliation: no session ID has to be known yet."""
    from laplace.writing import records, sealed_reader
    from urllib.parse import urlencode
    if not isinstance(request_id,str) or not 1<=len(request_id)<=160 or not sealed_reader._PIN.fullmatch(str(manifest_id)):
        raise ValueError('Reader lookup needs its exact request and manifest identities.')
    # Copy these bounded headers at one captured index cut. This uses the normal
    # index lock; it does not skip a publication lock to manufacture quick NONE.
    with records.index_lock:
        saved=records.index(root)
        issued=list(saved.by_id.get('RINPUT-'+manifest_id[7:],[]))
        matches=list(saved.by_request.get((project,request_id),[]))
        terminal=records.raw_indexed_record(saved,matches[0]) if len(matches)==1 and matches[0]['record']=='writing-reader-refusal' else None
    if terminal:
        refused=sealed_reader.terminal_refusal(terminal).details['reader_refusal']
        if refused['manifest_id']!=manifest_id:raise ValueError('Reader request belongs to another input.')
        return {'profile':sealed_reader.PROFILE,'project':project,'request_id':request_id,'manifest_id':manifest_id,
            'effect':'NOT_ADMITTED','receipt':None,'reader_refusal':refused,'exact':True}
    if not issued or any(row.get('record')!='writing-reader-input' or row.get('project')!=project for row in issued):
        raise ValueError('Reader manifest is not issued in this project.')
    if len(matches)>1:raise ValueError('Reader request identity is ambiguous.')
    receipt=None
    if matches:
        turn=matches[0];profile=turn.get('reader_profile') or {}
        if (profile.get('profile')!=sealed_reader.PROFILE or profile.get('manifest_id')!=manifest_id
                or not sealed_reader._PIN.fullmatch(str(turn.get('reader_intent_sha256')))):
            raise ValueError('Request belongs to another input/ordinary turn or has an unavailable intent header.')
        receipt={'turn_id':turn['id'],'session_id':turn['session_id'],'request_id':request_id,
            'manifest_id':manifest_id,'intent_sha256':turn['reader_intent_sha256'],
            'read':{'http':{'method':'GET','url':'/authoring/session-turn?'+urlencode({
                'project':project,'id':turn['id'],'view':'turn'})}}}
    return {'profile':sealed_reader.PROFILE,'project':project,'request_id':request_id,'manifest_id':manifest_id,
            'effect':'RECORDED' if receipt else 'NONE','receipt':receipt,'exact':True}


def artifact_record(root: Path, project: str, artifact_id: str) -> dict | None:
    """Return bounded metadata for one unambiguous project-scoped ART receipt."""
    from laplace.work.author_history_metrics import artifact_record as metadata_record
    return metadata_record(Path(root),project,artifact_id)


def _failure_target(row: Mapping[str, Any]) -> tuple | None:
    payload = row.get("payload") if isinstance(row.get("payload"), Mapping) else {}
    for key in ("file", "node", "id", "key", "path", "run_id", "url"):
        if payload.get(key):
            return key, str(payload[key])
    edits = payload.get("edits")
    if isinstance(edits, list) and edits:
        if any(not isinstance(edit,Mapping) or not isinstance(edit.get('file'),str) or not edit['file'] for edit in edits):return None
        return ("edits", tuple(sorted((edit["file"],
                str(edit.get("line_start") or ""), str(edit.get("line_end") or ""))
                for edit in edits)))
    return None


def _failure_recovery_read(turn, row, records):
    """One original successful read, qualified by the same immutable journal cut."""
    if not records or row.get('_recovery_ambiguous') or row.get('project')!=turn.get('project') or row.get('turn_id')!=turn.get('id'):return None
    failure_order=(records.get('orders') or {}).get(row.get('id'))
    if not isinstance(failure_order,int):return None
    recovery=row.get('recovery') if isinstance(row.get('recovery'),Mapping) else {}
    operation=row.get('operation');payload=row.get('payload') or {}
    contract=recovery.get('contract') or {}
    from laplace.work.author_history_metrics import _read_handle
    help_scope=None
    if operation=='help' and contract.get('operation')=='help':
        help_scope=admission.selector_scope(payload,contract.get('input'))
    handles=[]
    for key in ('help','next_reads','required_reads'):
        value=recovery.get(key);handles.extend(value if isinstance(value,list) else [value] if isinstance(value,Mapping) else [])
    consumed=recovery.get('consumed_read_recovery')
    if isinstance(consumed,Mapping):handles.extend(consumed.get('next_reads') or [])
    exact=[]
    for handle in handles:
        if not isinstance(handle,Mapping):continue
        op=handle.get('operation');values=handle.get('payload')
        if isinstance(op,str) and isinstance(values,Mapping) and values.get('project',turn['project'])==turn['project']:
            exact.append((op,_canonical_read_payload(op,{key:value for key,value in values.items() if key!='project'})))
    for read in (records.get('read_receipts') or {}).values():
        if (read.get('record')!='writing-tool-read' or read.get('ambiguous')
                or read.get('project')!=turn['project'] or read.get('turn_id')!=turn['id']
                or not isinstance(read.get('_order'),int) or read['_order']<=failure_order
                or not re.fullmatch(r'(?:sha256:)?[a-fA-F0-9]{64}',str(read.get('output_sha256') or ''))):continue
        values=read.get('payload') or {}
        if values.get('project',turn['project'])!=turn['project']:continue
        value=_canonical_read_payload(str(read.get('operation')),{key:item for key,item in values.items() if key!='project'})
        matched=(help_scope is not None and read.get('operation')=='help'
                 and value==help_scope and admission.selector_scope(value,contract['input'])==value)
        if matched or (read.get('operation'),value) in exact:
            return {'read_id':read['id'],'operation':read['operation'],'output_sha256':read['output_sha256'],
                'basis':'Same retained help selector' if matched else 'Exact retained recovery handle',
                'read_handle':_read_handle(turn['project'],{'view':'record','id':'activity:journal:'+read['id']}),
                'recovers_read_goal':bool(matched or operation!='help' and read.get('operation')==operation),
                'task_completion_inferred':False}
    return None


def _failure_related_action(turn: Mapping[str, Any], row: Mapping[str, Any], records=None) -> dict | None:
    """Link original later operation evidence, never infer a retry or task repair."""
    if records is None or row.get('_recovery_ambiguous'):return None
    if not all(isinstance(turn.get(key),str) and turn[key] for key in ('project','id')):return None
    if row.get('project')!=turn.get('project') or row.get('turn_id')!=turn.get('id'):return None
    target = _failure_target(row)
    if target is None:return None
    operation = row.get("operation") or row.get("tool_name")
    if not isinstance(operation,str) or not operation:return None
    for action in turn.get("tool_actions") or []:
        if action.get('_recovery_ambiguous'):continue
        if action.get('project')!=turn.get('project') or action.get('turn_id')!=turn.get('id'):continue
        order=records.get('orders') or {}
        later=(isinstance(order.get(action.get('id')),int) and isinstance(order.get(row.get('id')),int)
               and order[action['id']]>order[row['id']])
        if (action.get("operation") == operation and _failure_target(action) == target
                and later
                and not action.get("error")
                and (action.get("outcome") or {}).get("ok") is not False
                and (action.get("outcome") or {}).get("status") not in {"FAILED", "REFUSED", "ERROR"}):
            from laplace.work.author_history_metrics import _read_handle
            if target[0]=='edits':
                files={item[0] for item in target[1] if item[0]}
                label=next(iter(files)) if len(files)==1 else 'recorded edit locations'
            else:label=target[1]
            return {'action_id':action['id'],'operation':operation,'target':label,
                    'read_handle':_read_handle(turn['project'],{'view':'record','id':'activity:journal:'+action['id']}),
                    'basis':'same_operation_target'}
    return None


def _has_failure_candidates(turn):
    reply=turn.get('reply') if isinstance(turn.get('reply'),Mapping) else {}
    return bool(turn.get('tool_failures') or reply.get('provider_issues'))


def _recovery_candidate(row,*,action=False):
    """Detach only join inputs; public immutable bodies stay shallow references."""
    from copy import deepcopy
    fields=('id','project','turn_id','operation','tool_name','tool_use_id','ts','error','reason','_recovery_order')
    value={key:deepcopy(row[key]) for key in fields if key in row}
    payload=row.get('payload') if isinstance(row.get('payload'),Mapping) else {}
    keys={'file','node','id','key','path','run_id','url','edits'}
    recovery=row.get('recovery') if isinstance(row.get('recovery'),Mapping) else {}
    contract=recovery.get('contract') if isinstance(recovery.get('contract'),Mapping) else {}
    schema=contract.get('input') if isinstance(contract.get('input'),Mapping) else {}
    properties=schema.get('properties') if isinstance(schema.get('properties'),Mapping) else {}
    if row.get('operation')=='help':keys.update(properties.keys())
    projected={key:item for key,item in payload.items() if key in keys and key!='edits'}
    if isinstance(payload.get('edits'),list):
        projected['edits']=[{key:edit[key] for key in ('file','line_start','line_end') if key in edit}
                            for edit in payload['edits'] if isinstance(edit,Mapping)]
    if row.get('operation')=='help':
        # Unknown keys remain markers: unknown-only input must not become bare
        # help after snapshotting. Their ignored bodies are not join metadata.
        projected.update({key:None for key in payload if key not in keys})
    value['payload']=deepcopy(projected)
    if action:
        outcome=row.get('outcome') if isinstance(row.get('outcome'),Mapping) else {}
        value['outcome']={key:deepcopy(outcome[key]) for key in ('ok','status') if key in outcome}
    else:
        def handle(item):
            return {key:deepcopy(item[key]) for key in ('operation','payload') if key in item} if isinstance(item,Mapping) else None
        value['recovery']={}
        for key in ('help','next_reads','required_reads'):
            item=recovery.get(key)
            if isinstance(item,list):value['recovery'][key]=[handle(row) for row in item]
            elif isinstance(item,Mapping):value['recovery'][key]=handle(item)
        consumed=recovery.get('consumed_read_recovery')
        if isinstance(consumed,Mapping):value['recovery']['consumed_read_recovery']={'next_reads':[handle(row) for row in consumed.get('next_reads') or []]}
        value['recovery']['contract']={key:deepcopy(contract[key]) for key in ('operation','input') if key in contract}
    if not action:value['_public_record']={key:item for key,item in row.items() if not key.startswith('_recovery_')}
    return value


def _failure_read_cut(records,selected_turns):
    """One request-local grouping from this same cut's original read receipts.

    The rich fold has no immutable by-turn read index. Pay one metadata pass
    only when selected turns have failures; never substitute mutable baselines
    or acquire a newer index cut. Groups retain the original order/ambiguity.
    """
    from copy import deepcopy
    with _LOCK:
        snapshots={};orders={}
        for requested in selected_turns:
            key=(requested.get('project'),requested.get('id'))
            live=(records.get('turns') or {}).get(key[1],requested)
            source=live if live.get('project')==key[0] else requested
            reply=source.get('reply') if isinstance(source.get('reply'),Mapping) else {}
            candidate={'id':key[1],'project':key[0],
                'tool_failures':[_recovery_candidate(row) for row in source.get('tool_failures') or []],
                'reply':{'provider_issues':[_recovery_candidate(row) for row in reply.get('provider_issues') or []]}}
            candidate['tool_actions']=([_recovery_candidate(row,action=True) for row in source.get('tool_actions') or []]
                                       if _has_failure_candidates(candidate) else [])
            for row in [*candidate['tool_failures'],*candidate['reply']['provider_issues'],*candidate['tool_actions']]:
                ident=row.get('id')
                row['_recovery_ambiguous']=not isinstance(ident,str) or not ident or ident in (records.get('recovery_ambiguities') or set())
                if ident and isinstance(row.get('_recovery_order'),int) and not row['_recovery_ambiguous']:
                    orders[ident]=row['_recovery_order']
            snapshots[key]=candidate
        groups={key:{} for key,candidate in snapshots.items() if _has_failure_candidates(candidate)}
        if groups:
            for ident,read in (records.get('read_receipts') or {}).items():
                key=(read.get('project'),read.get('turn_id'))
                if key in groups:
                    groups[key][ident]=deepcopy({name:read[name] for name in
                        ('id','record','project','turn_id','operation','payload','output_sha256','_order','ambiguous') if name in read})
                    if ident in (records.get('recovery_ambiguities') or set()):groups[key][ident]['ambiguous']=True
    return {**records,'_failure_orders':orders,'_failure_read_groups':groups,'_failure_turns':snapshots}


def _turn_failure_rows(turn: Mapping[str,Any], records=None) -> list[dict]:
    if records is not None:
        if '_failure_read_groups' not in records:
            if not _has_failure_candidates(turn):return []
            records=_failure_read_cut(records,[turn])
        turn=records['_failure_turns'].get((turn.get('project'),turn.get('id')),turn)
        groups=records['_failure_read_groups']
        records={**records,'orders':records['_failure_orders'],
                 'read_receipts':groups.get((turn.get('project'),turn.get('id')), {})}
    if not _has_failure_candidates(turn):return []
    def normalized(row):
        payload=row.get("payload") if isinstance(row.get("payload"),Mapping) else {}
        return {"operation":row.get("operation") or row.get("tool_name") or "project operation",
                "error":row.get("error") or row.get("reason") or "No failure detail was recorded.",
                "target":payload.get("file") or payload.get("node") or payload.get("id") or payload.get("key")
                         or payload.get("path") or payload.get("run_id") or payload.get("url") or ""}
    def fingerprint(row):
        value=normalized(row);return "\n".join(str(value[key]) for key in ("operation","error","target"))
    result=[];seen=set();canonical=set()
    for row in turn.get("tool_failures") or []:
        key=row.get("tool_use_id") or row.get("id") or fingerprint(row)
        if key in seen:continue
        read=_failure_recovery_read(turn,row,records)
        seen.add(key);canonical.add(fingerprint(row));result.append({"origin":"tool","record":row.get('_public_record',row),
            "resolved_later":bool(read and read['recovers_read_goal']),
            "recovery_read":read,"related_action":_failure_related_action(turn,row,records)})
    reply=turn.get("reply") if isinstance(turn.get("reply"),Mapping) else {}
    for row in reply.get("provider_issues") or []:
        key=row.get("tool_use_id") or row.get("id") or fingerprint(row)
        if key in seen or fingerprint(row) in canonical:continue
        read=_failure_recovery_read(turn,row,records)
        seen.add(key);result.append({"origin":"provider","record":row.get('_public_record',row),
            "resolved_later":bool(read and read['recovers_read_goal']),
            "recovery_read":read,"related_action":_failure_related_action(turn,row,records)})
    return result


def _turn_failure_view(turn,records):
    """Annotate detached public rows; immutable failures remain unchanged."""
    if '_failure_read_groups' not in records:records=_failure_read_cut(records,[turn])
    held=records['_failure_turns'].get((turn.get('project'),turn.get('id')),{})
    failures=[row.get('_public_record',row) for row in held.get('tool_failures') or []]
    issues=[row.get('_public_record',row) for row in (held.get('reply') or {}).get('provider_issues') or []]
    observations={id(item['record']):item for item in _turn_failure_rows(turn,records)}
    def observed(row):
        item=observations.get(id(row),{})
        return {**row,'resolved_later':bool(item.get('resolved_later')),
                'recovery_read':item.get('recovery_read'),'related_action':item.get('related_action')}
    result={**turn,'tool_failures':[observed(row) for row in failures]}
    if isinstance(turn.get('reply'),Mapping):
        result['reply']={**turn['reply'],'provider_issues':[observed(row) for row in issues]}
    return result


def _artifact_result_links(turn: dict, records: dict, *, actions=None, limit: int = 21) -> list[dict]:
    """Join a turn's saved store actions to exact retained artifact metadata, without file reads."""
    project=str(turn.get('project') or '');links=[]
    for action in (_editor_actions(turn) if actions is None else actions):
        if action.get('operation')!='store_artifact':continue
        outcome=action.get('outcome') or {};payload=action.get('payload') or {}
        if action.get('project') not in {None,project} or action.get('turn_id') not in {None,turn.get('id')}:continue
        ids=[x for x in outcome.get('receipts') or outcome.get('identities') or [] if isinstance(x,str) and x.startswith('ART-')]
        if len(set(ids))!=1:continue
        key=(project,ids[0])
        if key in records.get('artifact_ambiguities',set()):continue
        record=records.get('artifact_records',{}).get(key)
        if not record:continue
        scope=record.get('scope') or 'project';path=record.get('artifact_path') or record.get('path')
        pin=record.get('sha256');action_pin=(outcome.get('revisions') or {}).get('revision')
        if not path or not pin or action_pin!=pin:continue
        if record.get('turn_id') and record['turn_id']!=turn.get('id'):continue
        if record.get('artifact_path') and (payload.get('path')!=path or payload.get('scope','project')!=scope):continue
        try:human=artifacts.human_read(project,path,scope,pin,ids[0])
        except ValueError:continue
        links.append({**human,'action_id':action.get('id'),'turn_id':turn.get('id'),
                      'basis':'Exact retained store action and project-scoped artifact receipt',
                      'aliases':list(dict.fromkeys(x for x in [ids[0],path,record.get('path')] if x))})
        if len(links)>=limit:break
    return links


def _turn_reads() -> "session_projection.TurnReads":
    """This owner's body reads for one projection call (built per call, so module rebinding is honoured)."""
    return session_projection.TurnReads(
        proposal_view=proposal_view, failure_rows=_turn_failure_rows, failure_view=_turn_failure_view,
        editor_actions=_editor_actions, applications=_applications, applied_edits=_applied_edits,
        artifact_result_links=_artifact_result_links)


def _session_turn_summary(source: dict, records: dict, *, bounded: bool = False) -> dict:
    """Conversation text and counts without eager action/proposal bodies (session_projection.turn_summary)."""
    return session_projection.turn_summary(source, records, reads=_turn_reads(), bounded=bounded)


def _application_receipt_for_edit(receipts:list[dict],edit:dict,index:int) -> dict:
    """Match owner coordinates; only wholly coordinate-free legacy rows use position."""
    located=[];matches=[]
    for receipt in receipts:
        if not isinstance(receipt,dict):continue
        owner=receipt.get("receipt") if isinstance(receipt.get("receipt"),dict) else receipt
        file,lines=owner.get("file"),owner.get("lines")
        if not (isinstance(file,str) and isinstance(lines,list) and len(lines)==2
                and all(isinstance(value,int) for value in lines)):continue
        located.append(receipt)
        if (file==edit.get("file") and lines[0]<=int(edit.get("line_start") or 0)
                and lines[1]>=int(edit.get("line_end") or 0)):
            matches.append(receipt)
    if len(matches)==1:return matches[0]
    if located:return {}
    return receipts[index] if index<len(receipts) and isinstance(receipts[index],dict) else {}


def _application_receipts_with_records(root:Path,project:str,receipts:list[dict]) -> list[dict]:
    """Join owner receipt row_ids to the canonical feedback rows at read time."""
    from laplace.manuscript import manuscript_bridge, manuscript_source
    source=manuscript_source.resolve(project,repo_root=root)
    md=(root/str(source.get("manuscript_dir") or "")).resolve()
    if not md.is_relative_to(root) or not md.is_dir():return receipts
    records=manuscript_bridge.feedback_list(
        root,project,ledger=md/"feedback"/"feedback.jsonl").get("records") or []
    by_id={row.get("id"):row for row in records if isinstance(row,dict) and row.get("id")}
    served=[]
    for receipt in receipts:
        if not isinstance(receipt,dict):served.append(receipt);continue
        owner=receipt.get("receipt") if isinstance(receipt.get("receipt"),dict) else receipt
        record=receipt.get("record") if isinstance(receipt.get("record"),dict) else None
        record=record or by_id.get(owner.get("row_id"))
        served.append({**receipt,**({"record":record} if isinstance(record,dict) else {})})
    return served


def session_turn_detail(root: Path, project: str, ident: str, view: str,
                        offset: int = 0, limit: int = 20, item_id: str = "") -> dict:
    """Lazy exact turn/action/failure detail over the immutable journal index."""
    root = Path(root).resolve()
    if view == 'failures':
        from laplace.writing.records import selected_failure_records
        records=selected_failure_records(root,project,ident)
    else:records = _records(root)
    source = records["turns"].get(ident)
    if not source or source.get("project") != project:
        raise ValueError("Unknown writing turn.")
    source=_parent_continuation_view(root,source)
    if view in {'turn','summary','failures'}:
        records=_failure_read_cut(records,[source])
    offset=max(0,int(offset));limit=max(1,min(50,int(limit)))
    if view == "turn":
        turn=_turn_failure_view(source,records);turn["actions"]=_editor_actions(turn);turn.update(proposal_view(turn,records=records))
        if turn.get("proposal"):
            from laplace.manuscript.manuscript_proposals import proposal_version
            turn.setdefault("proposal_version", proposal_version(source)[0])
        if isinstance(turn.get("reply"),dict):turn["reply"]={**turn["reply"],"actions":turn["actions"]}
        return {"project":project,"turn":turn,"exact":True,
                "note":"Exact saved public turn; provider-private reasoning is not stored or reconstructed."}
    if view == "summary":
        return {"project":project,"turn":_session_turn_summary(source,records),"exact":True}
    if view == "controls":
        execution = child_execution(root, source["session_id"])
        rows = _child_control_rows(root, source["session_id"], ident,
              execution.get("state") if execution.get("turn_id") == ident else "FINISHED",
              offset=offset,limit=limit,item_id=item_id)
        if item_id and not rows:raise ValueError("Unknown addressed control.")
        total = len(list(_steer_mailbox(root,source["session_id"]).glob("*.request.json"))) if not item_id else len(rows)
        page=rows
        return {"view":view,"project":project,"turn_id":ident,"items":page,"exact":True,
                "pagination":{"offset":offset,"limit":limit,"total":total,
                              "next_offset":offset+len(rows) if offset+len(rows)<total else None}}
    if view == "application":
        application=next((row for row in _applications(source) if row.get("id")==item_id),None)
        if application is None:raise ValueError("Unknown writing application.")
        edits=[];receipts=_application_receipts_with_records(
            root,project,list(application.get("receipts") or []))
        for index,edit in enumerate(_applied_edits(source,application)):
            receipt=_application_receipt_for_edit(receipts,edit,index)
            record=receipt.get("record") if isinstance(receipt.get("record"),dict) else {}
            anchor=record.get("anchor") if isinstance(record.get("anchor"),dict) else {}
            owner_receipt=receipt.get("receipt") if isinstance(receipt.get("receipt"),dict) else receipt
            owned_files=(application.get('owned_changes') or {}).get('files') or []
            manuscript_dir=(source.get('document') or {}).get('manuscript_dir') or ''
            expected_path=(Path(manuscript_dir)/str(edit.get('file') or '')).as_posix()
            pins=[row for row in owned_files if row.get('path')==expected_path]
            pin=pins[0] if len(pins)==1 else {}
            edits.append({**edit,"undo_basis":{
                "preimage_version_id":None,
                "postimage_version_id":owner_receipt.get("version_id"),
                "before_sha256":pin.get('before_sha256'),"after_sha256":pin.get('after_sha256'),
                "preimage_identity":"PINNED" if pin.get('before_sha256') else "UNAVAILABLE",
                "record_id":owner_receipt.get("row_id") or record.get("id"),
                "file":owner_receipt.get("file") or anchor.get("file") or edit.get("file"),
                "lines":owner_receipt.get("lines") or anchor.get("lines")
                        or [edit.get("line_start"),edit.get("line_end")],
                "basis":"Owned before/after file identities plus the exact recorded inverse rewrite; the editor-save version is post-write, not a preimage."}})
        return {"project":project,"turn_id":ident,"view":view,"exact":True,
                "application":{**application,"receipts":receipts,"edits":edits}}
    if view == "actions":
        rows=_editor_actions(source)
        page_actions=rows[offset:offset+limit]
        links={row["action_id"]:row for row in _artifact_result_links(source,records,actions=page_actions,limit=50)}
        rows=[{**row,"outcome":{**(row.get("outcome") or {}),
               **({"human_read":links[row.get("id")]} if row.get("id") in links else {})}}
              if row.get("id") in links else row for row in rows]
    elif view == "failures":
        rows=_turn_failure_rows(source,records)
    else:
        raise ValueError("session turn detail view must be summary, actions, failures, controls, application, or turn")
    page=rows[offset:offset+limit]
    return {"project":project,"turn_id":ident,"view":view,"items":page,
            "pagination":{"offset":offset,"limit":limit,"total":len(rows),
                          "next_offset":offset+len(page) if offset+len(page)<len(rows) else None},
            "exact":True}


def _parent_continuation_view(root, source):
    continuation=(source.get('reply') or {}).get('parent_continuation')
    if not continuation:return source
    from laplace.writing import dispatch_parent
    return {**source,'parent_continuation':dispatch_parent.public(root,source['project'],continuation)}


def session_state(root: Path, ident: str, before: str = "", *,
                  view: str = "full", limit: int | None = None) -> dict:
    root = Path(root).resolve()
    records = _records(root)
    session = records["sessions"].get(ident)
    if not session:
        raise ValueError("Unknown writing session.")
    turns = [dict(t) for t in records["turns"].values() if t.get("session_id") == ident]
    if before:
        position = next((i for i,t in enumerate(turns) if t['id']==before), None)
        if position is None: raise ValueError("Unknown conversation history cursor.")
        turns = turns[:position]
    if view not in {"full", "summary"}:
        raise ValueError("session view must be full or summary")
    page_limit = max(1,min(100,int(limit if limit is not None else (20 if view == "summary" else 100))))
    selected_turns=turns[-page_limit:]
    records=_failure_read_cut(records,selected_turns)
    # the page itself is a passive projection (laplace.writing.session_projection.session_page); this owner
    # adds only what is live: the running job, child execution and the recovery note
    def rewire_index(project):
        from laplace.research import corpus_ingest
        return {row['id']: row for row in corpus_ingest.rewire_list(root, project) if row.get('id')}
    page, newest = session_projection.session_page(
        selected_turns, records, session, view=view, reads=_turn_reads(),
        continuation=lambda source: _parent_continuation_view(root, source), rewire_index=rewire_index)
    with _LOCK:
        active = next((job for job in _JOBS.values() if job["session_id"] == ident and not job["done"]), None)
    session_view = dict(session)
    if session.get('reader_profile'):
        from laplace.writing.sealed_reader import capabilities
        session_view['reader_capabilities']=capabilities(session['reader_profile'],session['project'])
    advertised = context_window_advertised(session_view.get("provider", ""), session_view.get("model", ""))
    if advertised is not None:
        session_view["context_window_advertised"] = advertised
    active_view = None
    # the time of this owner observation of the running job or child host (the read time, as the Work owner's in-app
    # observed_at is); the conversation list and the navigation show it beside every running word they display
    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if active and not before:
        active_view = {"id": active["id"], "text": active["text"], "progress": active["progress"], "observed_at": observed_at,
                       "cursor": len(active["events"]), "turn_id":active["id"], "session_id":ident,"work_id":active.get("work_id"),
                       "capabilities": {"observation":"events", "events_url":"/authoring/events?turn="+active["id"],
                                        "can_interrupt":True, **_provider_controls(active.get("provider"))}}
        for key in ("usage", "usage_selection", "context_window_advertised", "context_window_effective", "context_tokens_used"):
            if active.get(key) is not None:
                active_view[key] = active[key]
        if active.get('parent_continuation'):active_view['parent_continuation']=active['parent_continuation']
    if active_view is None and not before:
        execution = child_execution(root, ident)
        if execution.get("state") in {"STARTING", "WAITING", "RUNNING", "ORPHANED"}:
            active_view = {"id": execution.get("turn_id"), "text": "",
                           "progress": execution["state"], "cursor": 0, "observed_at": observed_at,
                           "control": execution.get("last_control"), "turn_id":execution.get("turn_id"), "session_id":ident,
                           "capabilities": {"observation":"snapshot", "events_url":None,
                              "snapshot_url":_session_snapshot_url(session.get("project"),ident), "poll_interval_ms":500,
                              "can_interrupt":execution.get("state") in {"STARTING","WAITING","RUNNING","ORPHANED"},
                              "can_steer":execution.get("state")=="RUNNING" and bool(execution.get("remote_steering")) and bool((execution.get("control_capabilities") or {}).get("can_steer")),
                              "can_offer_input":execution.get("state")=="RUNNING" and bool((execution.get("control_capabilities") or {}).get("can_offer_input")),
                              "input_delivery_modes":(execution.get("control_capabilities") or {}).get("input_delivery_modes",[])}}
    from laplace.writing.session_settings import handle as settings_read
    return {"session": session_view, "turns": page,
            'settings_read':settings_read(session['project'],{'action':'read','target':{'kind':'conversation','session_id':ident}}),
            **({"usage_meter_turn_id": newest.get("id")} if view == "summary" and newest is not None else {}),
            "actions": [action for turn in page for action in turn.get("actions", [])],
            "older_cursor": page[0]['id'] if len(turns)>len(page) else None,
            "view": view,
            "active": active_view,
            "execution": child_execution(root, ident, controls=True),
            "recovery": "The previous turn has no final reply. Saved changes and proposals are retained below; nothing is replayed automatically."
            if turns and not turns[-1].get("reply") and not active_view else None}


def pending_proposals(root: Path, project: str, *, summary: bool = False, turn_id: str = '', **query) -> dict:
    from laplace.manuscript.proposal_navigation import read
    return read(root,project,{**query,**({'turn_id':turn_id} if turn_id else {})})


from laplace.writing.turn_jobs import _JOBS  # noqa: E402  (cycle-safe: imported last, as the door did)
from laplace.writing.child_hosts import (  # noqa: E402
    _child_control_rows, _provider_controls, _session_snapshot_url, _steer_mailbox, child_execution)
