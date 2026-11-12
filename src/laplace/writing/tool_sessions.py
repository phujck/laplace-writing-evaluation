"""NATIVE SESSION ADAPTERS (S1 B8): the current conversation's settings and history.

The original operation-table branch bodies, unchanged, each called once from
writing.operations._execute_sessions after the one admission. Every read is scoped to the caller's
exact current turn in this project.

  session_settings          the session summary, providers, a child's admitted return contract.
  session_settings_change   the owner's configure_session for this turn's session.
  conversation_history      earlier turns of this conversation, or one turn's control history.
"""
from __future__ import annotations

from pathlib import Path

from laplace.writing import records as writing_records


def _settings_caller(root, project, turn_id):
    """Exact caller fields, without hydrating conversation bodies or return schemas."""
    index = writing_records.index(root)
    turns = [row for row in index.by_id.get(turn_id, ())
             if row.get('record') == 'writing-turn' and index.project(row) == project]
    if len(turns) != 1:
        raise ValueError("Session settings requires this project's current logical turn.")
    turn = writing_records.selected_journal_fields(project, turn_id, root,
        fields=['id', 'project', 'session_id', 'dispatch_id', 'mode', 'connected_observation'])
    if not any(row.get('record') == 'writing-session' and index.project(row) == project
               for row in index.by_id.get(turn['session_id'], ())):
        raise ValueError("Session settings requires this project's current logical turn.")
    return turn


def session_settings(root: Path, project: str, payload: dict, turn_id: str | None) -> dict:
    turn = _settings_caller(root, project, turn_id)
    connection = turn.get('connected_observation') or {'available': False, 'reason':
        'No connected observation budget was admitted for this author turn; no implicit wait/relaunch is authorized.'}
    selected = payload.get('view', 'summary')
    if selected=='pilot':
        from laplace.writing import session_settings as owner
        values=payload.get('request') or {'action':'read','target':{'kind':'conversation','session_id':turn['session_id']}}
        if values.get('action') not in {'read','request'}:raise ValueError('Session settings inspection cannot mutate.')
        return owner.request(root,project,values,door={'origin':'native','turn_id':turn_id,'mode':turn['mode']})
    if selected == 'connection':
        return {'caller_turn_id': turn_id, 'session_id': turn['session_id'], 'project': project,
                'connected_observation': connection}
    from laplace.writing import session_reads
    from laplace.writing import dispatch_execution
    child_contract=dispatch_execution._child_return_contract(root,project,turn['session_id'],turn.get('dispatch_id'),turn_id=turn_id) if turn.get('dispatch_id') else None
    if selected in {'return-contract','return-schema'}:
        if not child_contract:raise ValueError('This actor has no admitted child return contract; use dispatch_status for parent synthesis.')
        return ({'caller_turn_id':turn_id,'schema_id':child_contract['schema_id'],'schema':child_contract['schema']}
            if selected=='return-schema' else {'caller_turn_id':turn_id,'return_contract':{
                key:value for key,value in child_contract.items() if key!='schema'}})
    data = session_reads.session_state(root, turn["session_id"], view="summary", limit=1)
    from laplace.writing import provider_catalogue
    catalogue = provider_catalogue.provider_catalogue(root)
    return {"session": data["session"], "providers": catalogue.get('providers', []),
        'provider_observation': {**{key: catalogue.get(key) for key in ('observed_at', 'updated_at', 'observation_scope', 'cached')},
            'mode': 'passive', 'meaning': 'Recorded or unknown capability metadata; not fresh service validation. Explicit refresh and selected settings admission remain separate.'},
        **({'return_contract':{key:value for key,value in child_contract.items() if key!='schema'},
            'scoped_permissions':[{'publication_context':child_contract['publication_context']}]} if child_contract else {}),
        'connected_observation': connection}


def session_settings_change(root: Path, project: str, payload: dict, turn_id: str | None) -> dict:
    if payload.get('action') in {'change','withdraw'}:
        from laplace.writing import session_settings as owner
        caller=_settings_caller(root,project,turn_id)
        return owner.request(root,project,payload,door={'origin':'native','turn_id':turn_id,'mode':caller['mode']})
    from laplace.writing import turn_admission
    records = writing_records.fold_records(root)
    turn = records["turns"].get(turn_id)
    if not turn or turn.get("project") != project:
        raise ValueError("Session settings requires this project's current logical turn.")
    return turn_admission.configure_session(root, project, turn["session_id"], payload)


def conversation_history(root: Path, project: str, payload: dict, turn_id: str | None) -> dict:
    from laplace.writing import session_reads
    from laplace.writing import session_projection
    if payload.get('view')=='message':
        allowed={'project','view','session_id','turn_id','part','offset','limit','expected_basis'}
        if set(payload)-allowed:raise ValueError('Select one closed conversation message read.')
        caller=_settings_caller(root,project,turn_id)
        if payload.get('project',project)!=project or payload.get('session_id')!=caller['session_id']:
            raise ValueError('Public message reads require the actual caller logical conversation.')
        return session_reads.public_message(root,{'project':project,
            **{key:value for key,value in payload.items() if key not in {'view','project'}}})
    records = writing_records.fold_records(root)
    turn = records["turns"].get(turn_id)
    if not turn or turn.get("project") != project:
        raise ValueError("Conversation history requires this project's current logical turn.")
    if payload.get("view") == "controls":
        target = records["turns"].get(str(payload.get("turn_id") or turn_id)) or {}
        parent = records["turns"].get(target.get("parent_turn_id")) or {}
        if (target.get("project") != project or
                target.get("session_id") != turn["session_id"] and parent.get("session_id") != turn["session_id"]):
            raise ValueError("Control history requires this conversation or one of its exact dispatched children.")
        return session_reads.session_turn_detail(root, project, target["id"], "controls",
            int(payload.get("offset") or 0), int(payload.get("limit") or 20), str(payload.get("item_id") or ""))
    data = session_reads.session_state(root,turn["session_id"],str(payload.get("before") or ""))
    rows = [row for row in data["turns"] if row["id"] != turn_id]
    limit = max(1,min(10,int(payload.get("limit",6))))
    selected = rows[-limit:]
    history = []
    for row in selected:
        answer = session_projection.reply_presentation_text(row.get("reply"))
        question = str(row.get("text") or "")
        history.append({"id":row["id"],"question":question[:2000],"answer":str(answer)[:4000],
                        "truncated":len(question)>2000 or len(str(answer))>4000})
    return {"session_id":turn["session_id"],"turns":history,
            "older_cursor":selected[0]["id"] if selected and (len(rows)>limit or data.get("older_cursor")) else None}
