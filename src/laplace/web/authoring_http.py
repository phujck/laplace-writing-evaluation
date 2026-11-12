"""THE AUTHORING HTTP DOOR (S1 B4): one /authoring/* request -> its family handler -> the domain owner.

authoring_surface.handle(path, query, method, body) is the door the scanner routes through: it fences the prefix and
the event stream, resolves the root once (authoring_surface._root) and hands it here explicitly.
Nothing here resolves a root, a cwd, a home or a profile.

  handle         parse the envelope, route, render. Its if-chain is the one place each route is
                 dispatched; tools/writing_verbs/http_routes.csv and writing_declared_http cite it.
  _parse         a POST body is one JSON object; the project coordinate (body, then query).
  _value         one query field, the first occurrence (the event stream reads it too).
  family handlers, each query admission then one domain-owner call:
    read_*       health, projects, providers, state, history, document, context, previews, undo
    session_*    one saved session and one turn's detail
    inspect_help the workspace's own help and a recorded turn's role-scoped help (D semantics)
    build        a build job, a build target, or the selected source's PDF build and status
  _ok / _refused / _failed / _NOT_FOUND
                 the unchanged 200 / 409 / 500 / 404 status, media type and JSON body.

Turn, control, proposal and source-edit routes call their owner directly from the router, reading the
owner's module attribute at call time (turn_admission, turn_control, session_reads, source_application, ...),
so the owner is also the test seam.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
import threading
from pathlib import Path
from typing import NamedTuple

from laplace.pipeline import registry
from laplace.writing import records as writing_records
from laplace.writing.provider import ProviderError

_JSON = "application/json; charset=utf-8"
_NOT_FOUND = (404, "application/json", b'{"error":"Unknown authoring operation"}')


class Request(NamedTuple):
    root: Path
    path: str
    method: str
    query: dict
    payload: dict
    project: str


def _value(query, name, default=""):
    value = query.get(name, default)
    return str(value[0] if isinstance(value, list) else value or default)


def _parse(root: Path, path: str, query: dict, method: str, body: bytes) -> Request:
    payload = json.loads(body or b"{}") if method == "POST" else {}
    if not isinstance(payload, dict):
        raise ValueError("Expected an object.")
    project = str(payload.get("project") or _value(query, "project") or _value(query, "corpus"))
    return Request(root, path, method, query, payload, project)


def handle(root: Path, path: str, query: dict, method: str, body: bytes):
    """Route one /authoring/* request (the facade has already fenced the prefix and the event stream)."""
    try:
        r = _parse(root, path, query, method, body)
        from laplace.pipeline import authoring
        if method == "GET" and path == "/authoring/health":
            data = read_health(r)
        elif method == "GET" and path == "/authoring/projects":
            data = read_projects(r)
        elif method == "GET" and path == "/authoring/providers":
            data = read_providers(r)
        elif method == "GET" and path == "/authoring/state":
            data = read_state(r)
        elif method == "GET" and path == "/authoring/history":
            data = read_history(r)
        elif method == "GET" and path == "/authoring/document":
            data = read_document(r)
        elif method == "GET" and path == "/authoring/context":
            # The ordinary workspace read needs current source only.  Full
            # historical receipt audits remain available by naming one exact
            # context_id; rebuilding every prior receipt made a 61-page
            # manuscript open take seconds on each refresh.
            data = authoring.inspect(r.project, repo_root=root, context_id=_value(query, "context_id", ""))
        elif method == "GET" and path == "/authoring/proposals":
            data = read_proposals(r)
        elif method == "GET" and path == "/authoring/proposal-preview":
            data = read_proposal_preview(r)
        elif method == "GET" and path == "/authoring/change-preview":
            from laplace.manuscript import manuscript_fragments
            data = manuscript_fragments.change_preview(r.project, {"file": _value(query, "file"), "id": _value(query, "id")}, root)
        elif method == "GET" and path == "/authoring/structural-undo":
            data = read_structural_undo(r)
        elif method == "POST" and path == "/authoring/proposal-decision":
            from laplace.manuscript import manuscript_proposals
            data = manuscript_proposals.decide(root, r.project, r.payload)
        elif path == "/authoring/build" and method in {"GET", "POST"}:
            return build(r)
        elif method == "GET" and path == "/authoring/session":
            data = session_read(r)
        elif method == "GET" and path == "/authoring/help":
            data = inspect_help(root, query)
        elif method == "GET" and path == "/authoring/session-turn":
            data = session_turn_read(r)
        elif path == '/authoring/reader' and method in {'GET','POST'}:
            from laplace.writing import sealed_reader
            if method=='POST':
                values=dict(r.payload)
                if values.pop('action',None)!='prepare':raise ValueError('Reader POST accepts only explicit prepare.')
                values['view']='prepare'
            else:
                values={key:_value(query,key) for key in query}
                if values.get('view')=='prepare':raise ValueError('Use explicit POST to prepare a reader packet.')
                if 'input' in values:values['input']=json.loads(values['input'])
                for key in ('offset','limit'):
                    if key in values:values[key]=int(values[key])
            if values.get('project')!=r.project:raise ValueError('Reader project differs from the caller.')
            data=sealed_reader.request(root,values)
        elif path == "/authoring/session-settings" and method in {"GET","POST"}:
            from laplace.writing import session_settings
            if method=='GET' or 'action' in r.payload:
                data=session_settings.http_request(root,r.project,path,query,method,r.payload,raw_body=body)
            else:
                if set(r.payload)-{'project','session_id','provider','model','effort'}:raise ValueError('Session settings contain unsupported preference fields.')
                data = turn_admission.configure_session(root, r.project, str(r.payload.get("session_id") or ""), r.payload)
        elif method == "POST" and path == "/authoring/argument":
            data = authoring.save(r.project, r.payload, repo_root=root)
        elif method == "POST" and path == "/authoring/chapter":
            from laplace.manuscript import manuscript_structure
            data = manuscript_structure.create_chapter(r.project, r.payload.get("title", ""), root,
                                                       expected_root_digest=r.payload.get("expected_root_digest"))
        elif method == "POST" and path == "/authoring/section-change":
            from laplace.manuscript import manuscript_structure
            data = manuscript_structure.change(r.project, r.payload, root)
        elif method == "POST" and path == "/authoring/block-change":
            from laplace.manuscript import blocks as manuscript_blocks
            data = manuscript_blocks.change(root, r.project, r.payload)
        elif method == "POST" and path == "/authoring/correction":
            data = authoring.bank_correction(r.project, r.payload, repo_root=root)
            if 'review_route' in r.payload and data.get('effect')=='RECORDED':
                from laplace.work import work_delivery
                # The origin owner has released source/authoring/feedback locks.
                # This human door cannot invent native parent provenance.
                try:
                    route=work_delivery.compose_origin(root,r.project,data,r.payload['review_route'],
                                                       door={'origin':'human'})
                except Exception as exc:
                    route={'effect':'UNKNOWN','error':str(exc)[:240],
                           'note':'Comment saved; route outcome is not confirmed. Reconcile the same submission.'}
                data={**data,'review_route':route}
        elif method == "POST" and path == "/authoring/correction-prepare":
            data=authoring.prepare_correction(r.project,r.payload,repo_root=root)
        elif method == "POST" and path == "/authoring/correction-settle":
            data=authoring.settle_correction(r.project,r.payload,repo_root=root)
        elif method == "GET" and path == "/authoring/correction-request":
            data=authoring.correction_request(r.project,_value(query,'request_id'),repo_root=root,
                                             ledger=_value(query,'ledger'),submission=_value(query,'submission') or None)
        elif method == "GET" and path == "/authoring/correction-origin":
            data=authoring.correction_origin(r.project,json.loads(_value(query,'origin_ref')),repo_root=root)
        elif method == "POST" and path == "/authoring/correction-status":
            data = authoring.correction_status(r.project, r.payload, repo_root=root)
        elif method == "POST" and path == "/authoring/edition":
            from laplace.manuscript import manuscript_source
            data = manuscript_source.select(r.project, r.payload["root"], repo_root=root,
                                            expected_revision=r.payload.get("base_revision"))
        elif method == "POST" and path == "/authoring/turn":
            data = turn_admission.start_turn(root, r.payload)
        elif method == "POST" and path in ("/authoring/interrupt", "/authoring/steer"):
            data = turn_control.interrupt_turn(root, r.payload) if path.endswith("interrupt") else turn_control.steer_turn(root, r.payload)
        elif method == "POST" and path == "/authoring/apply":
            data = source_application.apply_proposal(root, r.payload)
        else:
            return _NOT_FOUND
        return _ok(data)
    except (ValueError, KeyError, ProviderError) as exc:
        return _refused(exc)
    except Exception as exc:
        return _failed(exc)


def _ok(data) -> tuple:
    return 200, _JSON, json.dumps(data, ensure_ascii=False, default=str).encode()


def _exact(data, code: int = 200) -> tuple:
    """The build door's early answers keep their original ASCII serialisation."""
    return code, _JSON, json.dumps(data).encode()


def _refused(exc: BaseException) -> tuple:
    # The HTTP door for section-change, chapter, block-change and correction-status: the
    # same `refused` block the tool door serves, on the path that had no resolver at all.
    from laplace.core import identity_doors
    from laplace.work.project_work import conflict_details
    from laplace.manuscript.build_jobs import error_details as build_job_error_details
    from laplace.manuscript.build_targets import error_details as build_target_error_details
    from laplace.manuscript.proposal_currentness import proposal_refusal_details
    from laplace.manuscript.source_effects import error_details
    from laplace.pipeline.workflow_definitions import Refused as WorkflowRefused
    from laplace.writing.sealed_reader import error_details as reader_error_details
    from laplace.writing.session_reads import message_refusal_details
    from laplace.writing.session_settings import error_details as settings_error_details
    return 409, _JSON, json.dumps(
        identity_doors.body(exc, {"error": str(exc), **error_details(exc),
                                 **({'refused': exc.details} if isinstance(exc, WorkflowRefused) else {}),
                                 **proposal_refusal_details(exc), **conflict_details(exc),
                                 **build_target_error_details(exc), **build_job_error_details(exc),
                                 **reader_error_details(exc), **message_refusal_details(exc), **settings_error_details(exc)})).encode()


def _failed(exc: BaseException) -> tuple:
    return 500, _JSON, json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode()


def read_health(r: Request) -> dict:
    from laplace.manuscript import document_style, manuscript_figure_preview
    from laplace.research import formal_surface
    from laplace.research import research_runs
    active_runs=research_runs.active_runs(r.root)
    active_work,active_work_omitted=turn_jobs.active_work_projection(active_runs)
    with turn_jobs._ACTIVE_HTTP_MUTATIONS_LOCK:
        active_mutations=len(turn_jobs._ACTIVE_HTTP_MUTATIONS)
    return {"source": str(r.root.resolve()), "runtime": "writing" if os.environ.get("LAPLACE_WRITING_APP") == "1" else "scanner",
            "pid": os.getpid(), "python": sys.executable,
            "active_turns": turn_jobs.active_turn_count(),
            "active_previews": (len(document_style._JOBS)
                                + manuscript_figure_preview.active_renders()),
            "active_builds": sum(t.name == "writing-pdf-build" for t in threading.enumerate()),
            "active_runs": len(active_runs),
            "active_proof_checks": formal_surface.active_checks(),
            "active_mutations":active_mutations,
            "active_work":active_work,
            "active_work_omitted":active_work_omitted,
            "schema_version": "laplace.writing-health/2"}


def read_projects(r: Request) -> dict:
    return {"projects": [{"id": name, "name": p.manifest.get("display_name") or name}
                         for name, p in registry.all_projects(repo_root=r.root).items() if p.kind != "site"]}


def read_providers(r: Request) -> dict:
    if _value(r.query, "refresh") == "1":
        return writing_provider.capabilities(r.root, True)
    from laplace.writing.provider import provider_catalogue
    return provider_catalogue(r.root)


def read_state(r: Request) -> dict:
    from laplace.pipeline import authoring
    sessions = [dict(s) for s in session_reads._records(r.root)["sessions"].values() if s["project"] == r.project]
    limit = max(30,min(1000,int(_value(r.query,'session_limit','30'))))
    view = _value(r.query, "view", "")
    if view in {"", "full"}:
        data = authoring.load(r.project, repo_root=r.root)
        data["sessions"] = sessions[-limit:]
        data['session_count'] = len(sessions)
        return data
    if view == "sessions":
        return {"project": r.project, "sessions": sessions[-limit:], "session_count": len(sessions)}
    if view == "summary":
        return authoring.summary(r.project, repo_root=r.root)
    if view == "all-sessions":
        return read_session_index(r)
    raise ValueError("authoring state view must be full, summary, sessions, or all-sessions")


_SESSION_FILTERS = {"", "running", "waiting", "failed"}


def _session_index_row(session: dict, turns: list, all_turns: dict, sessions: dict, live: dict | None) -> dict:
    """One session of the cross-project index: the saved session record, its last saved turn and reply, and
    whether turn_jobs observes a live turn for it now. Every field is copied from an owner record."""
    last = turns[-1] if turns else None
    reply = (last or {}).get("reply") or {}
    parent_turn_id = next((t.get("parent_turn_id") for t in turns if t.get("parent_turn_id")), None)
    parent_turn = all_turns.get(parent_turn_id) if parent_turn_id else None
    parent_session = sessions.get((parent_turn or {}).get("session_id")) if parent_turn else None
    if live:
        state = "starting" if live.get("kind") == "turn-start" else "running"
    elif last is None:
        state = "no-turn"
    elif not reply:
        state = "no-reply"
    elif (reply.get("status") == "completed" and last.get("proposal_versions")
          and not last.get("proposal_decisions")):
        state = "waiting"
    else:
        state = str(reply.get("status") or "no-reply")
    live_turn = (live or {}).get("turn_id")
    running_turn = all_turns.get(live_turn) if live_turn else None
    times = [t for t in ((last or {}).get("ts"), reply.get("ts"), session.get("ts")) if isinstance(t, str)]
    return {"session_id": session.get("id"), "project": session.get("project"), "title": session.get("title"),
            "role": session.get("role"), "provider": session.get("provider"), "model": session.get("model"),
            "effort": session.get("effort"), "actual_model": session.get("actual_model"),
            "created_at": session.get("ts"), "state": state,
            "active": ({"kind": live.get("kind"), "turn_id": live_turn,
                        "since": (running_turn or {}).get("ts")} if live else None),
            "last_turn": ({"turn_id": last.get("id"), "at": last.get("ts"), "mode": last.get("mode"),
                           "status": reply.get("status"), "error": reply.get("error"),
                           "ended_at": reply.get("ts"),
                           "awaiting_proposal_decision": state == "waiting"} if last else None),
            "turn_count": len(turns),
            "tool_failures": sum(len(t.get("tool_failures") or ()) for t in turns),
            "parent": ({"turn_id": parent_turn_id, "session_id": (parent_turn or {}).get("session_id"),
                        "title": (parent_session or {}).get("title"),
                        "dispatch_id": next((t.get("dispatch_id") for t in turns if t.get("dispatch_id")), None)}
                       if parent_turn_id else None),
            "latest_at": max(times) if times else None}


def read_session_index(r: Request) -> dict:
    """GET /authoring/state?view=all-sessions: every saved writing session across projects (or one project when
    the request names it), live first, then waiting for the author, then the rest newest first; paged.

    Sources: the journal fold (session_reads._records: sessions, turns, replies, tool failures, proposal
    decisions) and turn_jobs.active_work_projection (this process's accepted turn starts, live turns and
    child-host records). Counts are over the project-filtered set before the state filter and the page."""
    state_filter = _value(r.query, "state", "")
    if state_filter not in _SESSION_FILTERS:
        raise ValueError("all-sessions state must be running, waiting or failed")
    limit = max(1, min(200, int(_value(r.query, "limit", "50") or 50)))
    offset = max(0, int(_value(r.query, "offset", "0") or 0))
    folded = session_reads._records(r.root)
    with session_reads._LOCK:
        sessions = {key: dict(value) for key, value in folded["sessions"].items()}
        all_turns = {key: dict(value) for key, value in folded["turns"].items()}
    live_rows, _omitted = turn_jobs.active_work_projection((), limit=1_000_000)
    live: dict[str, dict] = {}
    for row in live_rows:
        if row.get("kind") in {"turn", "turn-start"} and row.get("session_id"):
            live.setdefault(str(row["session_id"]), row)
    by_session: dict[str, list] = {}
    for turn in all_turns.values():
        by_session.setdefault(str(turn.get("session_id")), []).append(turn)
    rows = [_session_index_row(s, by_session.get(str(sid), []), all_turns, sessions, live.get(str(sid)))
            for sid, s in sessions.items()]
    projects: dict[str, int] = {}
    for row in rows:
        projects[str(row["project"])] = projects.get(str(row["project"]), 0) + 1
    if r.project:
        rows = [row for row in rows if row["project"] == r.project]
    rank = {"running": 0, "starting": 0, "waiting": 1}
    rows.sort(key=lambda row: str(row["latest_at"] or ""), reverse=True)
    rows.sort(key=lambda row: rank.get(row["state"], 2))
    counts = {"all": len(rows), "running": sum(row["state"] in {"running", "starting"} for row in rows),
              "waiting": sum(row["state"] == "waiting" for row in rows),
              "failed": sum(row["state"] == "failed" for row in rows)}
    if state_filter:
        wanted = {"running": {"running", "starting"}, "waiting": {"waiting"}, "failed": {"failed"}}[state_filter]
        rows = [row for row in rows if row["state"] in wanted]
    page = rows[offset:offset + limit]
    return {"schema_version": "laplace.session-index/1", "view": "all-sessions", "project": r.project or None,
            "state": state_filter or None, "counts": counts,
            "projects": [{"project": key, "sessions": value} for key, value in sorted(projects.items())],
            "total": len(rows), "offset": offset, "limit": limit,
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "sessions": page,
            "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "order_basis": "live turns first, then a completed turn whose recorded proposal has no recorded decision, "
                           "then the newest recorded turn, reply or session time",
            "live_basis": "turn_jobs.active_work_projection: accepted turn starts, live turns and child-host "
                          "records observed by this process at observed_at"}


def read_history(r: Request) -> dict:
    from laplace.work import history as author_history
    from laplace.pipeline import authoring
    project, root = r.project, r.root
    payload=author_history.http_history_payload(r.query)
    if payload.get("view") not in (None,"","corrections","activity","telemetry","record","source"):
        raise ValueError("author_history view must be corrections, activity, telemetry, or record")
    if payload.get("view")=="source":
        return author_history.source(project,payload,root)
    if payload.get("view")=="activity":
        author_history.validate_activity_query(payload)
        page=author_history.comparison_page(payload)
        return (author_history.detail(project,payload["id"],root,comparison_offset=page[0],comparison_limit=page[1]) if payload.get("id")
                else author_history.history(project,payload,root))
    if payload.get("view")=="telemetry":
        return author_history.telemetry(project,payload,root)
    if payload.get("view")=="record":
        if not payload.get("id"): raise ValueError("author_history record requires an exact id")
        return author_history.record(project,payload["id"],root)
    return authoring.history(project,payload,repo_root=root)


def read_document(r: Request) -> dict:
    from laplace.manuscript import build_targets, document
    query = r.query
    kind = _value(query,'target_kind','manuscript')
    if kind not in {'manuscript','derived','publication-edition'}:
        raise ValueError('target_kind must be manuscript, derived or publication-edition.')
    if _value(query,'view') in {'template','template-candidates'}:
        from laplace.manuscript import document_templates
        values={key:_value(query,key) for key in ('view','candidate_ref','preview_ref','part','file','offset','limit','page') if _value(query,key)!=''}
        for key in ('candidate_ref','preview_ref'):
            if key in values:values[key]=json.loads(values[key])
        for key in ('offset','limit','page'):
            if key in values:values[key]=int(values[key])
        return document_templates.inspect(r.project,values,r.root)
    return build_targets.read(r.project,r.root,target_kind=kind) if kind!='manuscript' else document.current(r.project, r.root)


def read_proposals(r: Request) -> dict:
    from laplace.manuscript.proposal_navigation import contract
    values={key:_value(r.query,key) for key in contract()['properties'] if _value(r.query,key)!=''}
    return session_reads.pending_proposals(r.root,r.project,**values)


def _declared_query_values(query, properties) -> dict:
    """Query text decoded to the type the proposal read contract declares, before any owner read: object/array
    fields arrive as JSON text and integers as digits; malformed values refuse here. limit stays text (the owner
    reads it so on every view)."""
    values={}
    for key,schema in properties.items():
        raw=_value(query,key)
        if raw=='':continue
        kind=schema.get('type')
        if kind in ('object','array'):
            try:decoded=json.loads(raw)
            except ValueError as error:raise ValueError('Proposal read '+key+' must be JSON '+kind+' text.') from error
            if not isinstance(decoded,dict if kind=='object' else list):raise ValueError('Proposal read '+key+' must be a JSON '+kind+'.')
            values[key]=decoded
        elif kind=='integer' and key!='limit':
            if not raw.isdigit():raise ValueError('Proposal read '+key+' must be a non-negative integer.')
            values[key]=int(raw)
        else:values[key]=raw
    return values


def read_proposal_preview(r: Request) -> dict:
    from laplace.manuscript.proposal_navigation import contract, read
    values=_declared_query_values(r.query,contract()['properties'])
    values.setdefault('id',_value(r.query,'turn_id'))
    values.setdefault('view','preview')
    return read(r.root,r.project,values)


def read_structural_undo(r: Request) -> dict:
    from laplace.work import history as author_history
    query = r.query
    if any(key not in {"project", "corpus", "kind", "id"} or len(values) != 1
           for key, values in query.items()):
        raise ValueError("Structural Undo query requires exact project, kind and id coordinates")
    if query.get("project") and query.get("corpus") and _value(query,"project") != _value(query,"corpus"):
        raise ValueError("Structural Undo project coordinates conflict")
    return author_history.structural_undo(r.project, {"view":"structural-undo",
        "kind":_value(query,"kind"), "id":_value(query,"id")}, r.root)


def session_read(r: Request) -> dict:
    query = r.query
    return session_reads.session_state(r.root, _value(query, "id"), _value(query,'before'),
                                 view=_value(query,"view","full"),
                                 limit=int(_value(query,"limit","20")))


def session_turn_read(r: Request) -> dict:
    query = r.query
    if _value(query,'view')=='message':
        allowed={'project','session_id','id','view','part','offset','limit','expected_basis'}
        if set(query)-allowed or any(isinstance(value,list) and len(value)!=1 for value in query.values()):
            raise ValueError('Select one closed project/session/turn message read.')
        payload={'project':r.project,'session_id':_value(query,'session_id'),
                 'turn_id':_value(query,'id'),'part':_value(query,'part')}
        for key in ('offset','limit'):
            if key in query:payload[key]=int(_value(query,key))
        if 'expected_basis' in query:payload['expected_basis']=_value(query,'expected_basis')
        return session_reads.public_message(r.root,payload)
    if _value(query,'view')=='reader-request':
        if set(query)-{'project','request_id','manifest_id','view'}:raise ValueError('Reader lookup needs project/request/manifest only.')
        return session_reads.reader_request(r.root,r.project,_value(query,'request_id'),_value(query,'manifest_id'))
    if _value(query, 'view') == 'request':
        if set(query) - {'project', 'session_id', 'request_id', 'view'}:
            raise ValueError('Submission reconciliation accepts only project, session_id, request_id and view.')
        return session_reads.turn_request(r.root, r.project, _value(query, 'session_id'), _value(query, 'request_id'))
    return session_reads.session_turn_detail(r.root, r.project, _value(query,"id"),
                                       _value(query,"view","turn"),
                                       int(_value(query,"offset","0")),
                                       int(_value(query,"limit","20")),
                                       _value(query,"item_id"))


def build(r: Request) -> tuple:
    """GET or POST /authoring/build: an addressed job, an addressed target, else the selected source."""
    from laplace.manuscript import projection_viewer
    from laplace.manuscript import build_jobs, build_targets
    project, root, method = r.project, r.root, r.method
    # The one admitted build operation (build_jobs.admit), before any branch read or effect; the
    # branch is chosen from it alone and selectors are never decoded again here.
    admitted=build_jobs.admit(r.payload if method=='POST' else {key:_value(r.query,key) for key in build_jobs.SELECTORS if key in r.query},
                              project,read=method!='POST',query=method!='POST')
    if admitted['operation']=='job':
        job=admitted['build_job']
        return _exact(build_jobs.cancel(job,project,root) if method=='POST' else build_jobs.status(job,project,root))
    if admitted['operation']=='prepare':
        from laplace.manuscript import publication_editions
        return _exact(publication_editions.prepare(project,r.payload,root))
    if admitted['operation']=='target':
        target=admitted['build_target']
        if target.get('kind')=='candidate':
            if method=='GET':
                return _exact(build_targets.candidate_status(project,target,root))
            from laplace.manuscript import document_templates
            build_targets.stage_candidate(project,target['candidate_ref'],
                                          document_templates.candidate(project,target['candidate_ref'],root)['proposal'],root)
        build_targets.resolve(target,project,root)
        if method=='POST':
            code,data = projection_viewer.recompile(target['root'],project,'author',repo_root=root,build_target=target)
            return _exact(data, code)
        return _exact(projection_viewer.recompile_status(target['root'],repo_root=root,corpus=project,build_target=target))
    return _ok(_build_selected_source(r))


def _build_selected_source(r: Request) -> dict:
    """The selected manuscript source: POST starts its PDF build; GET is its status, with a condition token."""
    from laplace.manuscript import manuscript_source, projection_viewer
    project, root, query = r.project, r.root, r.query
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("status") != "resolved" or not source.get("root"):
        raise ValueError("Select a manuscript source before building a PDF.")
    if r.method == "POST":
        if source.get("read_only"):
            raise ValueError("This source is read-only. Build an editable working copy to produce a new PDF.")
        code, data = projection_viewer.recompile(source["root"], project, "author", repo_root=root, compile_root=source["root"], _selection=source)
        if code >= 400:
            raise ValueError(data.get("reason") or data.get("error") or "PDF build could not start.")
        return data
    from laplace.manuscript import document
    observed=document.current(project,root,source=source,include_preview=False)
    data={**observed['current_build'],**{key:observed[key] for key in
        ('project','selected_source','source_observation','presentation_revision','current_revision','observation_coherence')},
        'document_status':observed['status']}
    summary={key:value for key,value in data.items() if key not in {'log_tail','error_detail'}}
    # G17: the condition token covers the WHOLE delivered status projection (document
    # revision plus build identity, state, publication and freshness fields), so an
    # unchanged source with a new or finished build job is never reported unchanged.
    summary_revision='sha256:'+hashlib.sha256(json.dumps(summary,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
    known=_value(query,'known_revision','')
    if known and known==summary_revision:
        # The poller holds this exact projection; answer with the identities only.
        # The observation itself is still computed (source files are stat/hashed),
        # so this saves bytes, not the read.
        # H2 (M5 C7-C9 repair): the unchanged answer is the condition token and the
        # document status word only (the token already covers the source revision,
        # build identity, state, publication and freshness); under 300 bytes serialized
        return {'project':project,'unchanged':True,'summary_revision':summary_revision,
                'document_status':observed['status'],
                'as_of':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    data['summary_revision']=summary_revision
    if _value(query,'view','')=='summary':
        data={**summary,'summary_revision':summary_revision}
    return data


def inspect_help(root: Path, query: dict) -> dict:
    """Current human help: explicit namespace/role, no provider-read occurrence."""
    from jsonschema import Draft202012Validator
    from laplace.native import declarations as writing_declarations, tools as writing_tools

    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate help context field: " + key)
            value[key] = item
        return value

    value = {}
    for key, items in query.items():
        if not isinstance(items, (list, tuple)) or len(items) != 1 or not isinstance(items[0], str):
            raise ValueError("Help query fields must occur exactly once: " + key)
        value[key] = items[0]
    if "context" in value:
        try:
            value["context"] = json.loads(value["context"], object_pairs_hook=unique_object)
        except json.JSONDecodeError as exc:
            raise ValueError("Help context must be one JSON object") from exc
    error = next(Draft202012Validator(writing_declarations.help_http_contract()).iter_errors(value), None)
    if error is not None:
        raise ValueError("Help inspection query rejected: " + error.message)
    project = value.pop("project", "")
    if project and project not in registry.all_projects(repo_root=root):
        raise ValueError("Help project is unavailable")
    if value.get("view") in writing_declarations.HELP_OWNER_CONCEPTS:
        # THE WORKSPACE'S OWN HELP (G8): areas, journeys and controls from the declarations
        # the native `help {concept: areas}` read also renders. No role, no turn, no provider
        # read; bounded by the declaration and versioned for a once-per-session consumer.
        # view=areas is the whole once-per-session payload; the other views are one concept
        # (diagrams and the acceptance checklist are read when opened, C10).
        view = value["view"]
        if value.keys() - {"view"}:
            raise ValueError("a declarations read takes no role, turn or selector")
        return {"project": project,
                "inspection": {"binding": "declarations", "turn_id": None, "mode": None},
                "help": writing_declarations.help_areas(project, "" if view == "areas" else view)}
    turn_id = value.pop("turn_id", None)
    mode = value.pop("mode", None)
    if turn_id is not None:
        # Same addressed metadata cut used by existing history. No rich fold or
        # custody body is needed to establish original admitted project/role.
        with writing_records.index_lock:
            idx = writing_records.index(root)
            rows = idx.by_id.get(turn_id, ())
            if len(rows) != 1 or rows[0].get("record") != "writing-turn" or idx.project(rows[0]) != project:
                raise ValueError("Help requires one exact turn in this project")
            selected = writing_records.raw_indexed_record(idx, rows[0])
            if selected.get("project") != project:
                raise ValueError("Help requires an original turn in this project")
            mode = selected.get("mode")
        if mode not in {"work", "review", "revise", "discuss"}:
            raise ValueError("Saved turn role is unavailable; no role is inferred")
    response = writing_tools.help_response(root, project, mode, value,turn_id=turn_id)
    return {"project": project,
            "inspection": {"binding": "recorded-turn" if turn_id else "unbound-human",
                           "turn_id": turn_id, "mode": mode},
            "help": response}


from laplace.writing import turn_jobs
from laplace.writing import session_reads
from laplace.writing import provider as writing_provider
from laplace.writing import turn_admission
from laplace.writing import turn_control
from laplace.manuscript import source_application
