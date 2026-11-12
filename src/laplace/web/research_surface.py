"""The bounded research-compute surface: the /research/* HTTP entry and the compatibility facade.

This module is deliberately a handler, not a service: GET derives a small view
from declared project files and a requested job record; it never starts a
watcher, scans a corpus, materialises figures, or rebuilds an experiment.  The
only executable door is an explicitly declared project-relative producer.

Since the research family (core consolidation R1, 2026-10-19) this module holds only the HTTP entry: the route
table, each route's method/query/body admission and the JSON reply (writing.research_http). Everything else is
owned elsewhere and forwarded here as the same object, so every old name stays importable:
  writing.research_context       project/state-home resolution (project, owner_home, project_root, inside, repo_root)
  writing.research_observation   the one read ledger and its consumption primitives
  writing.research_catalogue     state_payload / state_read / catalogue_payload and the ONE state cache
  writing.research_presentation  pure per-record presentation joins
  writing.research_records       the record contract and constants, guarded record renewal, currentness, result_bindings
  writing.research_runs          producer/run constants and contracts, launch admission/activation, run status, cancel
  writing.research_artifact_read GET /research/artifact resolution and reads
The owners import none of this module; a seam a test needs is patched on the owner that reads it. The native
operation table (writing.operations) calls the owners directly; this entry and that table are two doors over
one implementation.
"""
from __future__ import annotations

import json
from pathlib import Path

from laplace.web import research_artifact_read
from laplace.research import research_catalogue, research_runs
from laplace.web.research_http import json_reply as _json, q1 as _q1


def handle(path: str, query: dict, method: str, body: bytes, repo_root=None) -> tuple[int, str, bytes] | None:
    """The /research/* door: fence, then the one route of this path (catalogue, record, run or artifact family).

    Each family route admits its own method, query and body and calls its owner with the explicit root."""
    if path != "/research" and not path.startswith("/research/"):
        return None
    method = (method or "GET").upper()
    project = _q1(query, "project") or _q1(query, "corpus")
    route = _ROUTES.get(path)
    if route is None:
        return _json(404, {"error": f"unknown research route {path!r}"})
    return route(project, query, method, body, repo_root)


def _body_object(body: bytes, not_object: str = "body must be an object"):
    """A POST body as one JSON object, or the route's refusal reply."""
    try:
        payload = json.loads(body or b"{}")
    except (ValueError, TypeError):
        return None, _json(400, {"error": "bad json"})
    if not isinstance(payload, dict):
        return None, _json(400, {"error": not_object})
    return payload, None


# ---- catalogue reads ---------------------------------------------------------------------------

def _state_route(project, query, method, body, repo_root):
    if method != "GET":
        return _json(405, {"error": "GET /research/state only"})
    if not project:
        return _json(400, {"error": "project= required"})
    return _json(*research_catalogue.state_read(project, repo_root, view=_q1(query, "view")))


def _result_route(project, query, method, body, repo_root):
    if method != "GET":return _json(405,{"error":"GET /research/result only"})
    if not project:return _json(400,{"error":"project= required"})
    return _json(*research_catalogue.state_read(project, repo_root, view="result", ident=_q1(query, "id")))


# ---- record writes -----------------------------------------------------------------------------

def _reconcile_route(project, query, method, body, repo_root):
    if method != 'POST': return _json(405, {'error':'POST only'})
    payload, refused = _body_object(body, 'body must be object')
    if refused: return refused
    return _json(*reconcile(project or payload.get('project',''), payload, root=repo_root))


def _record_route(project, query, method, body, repo_root):
    if method != "POST":
        return _json(405, {"error": "POST /research/record only"})
    payload, refused = _body_object(body)
    if refused: return refused
    return _json(*record(project or payload.get("project", ""), payload, root=repo_root))


# ---- producers and runs ------------------------------------------------------------------------

def _run_route(project, query, method, body, repo_root):
    if method != "POST":
        return _json(405, {"error": "POST /research/run only"})
    payload, refused = _body_object(body)
    if refused: return refused
    return _json(*launch(project or payload.get("project", ""), payload, root=repo_root))


def _producer_route(project, query, method, body, repo_root):
    if method != "POST": return _json(405,{"error":"POST /research/producer only"})
    payload, refused = _body_object(body, "body must be object")
    if refused: return refused
    return _json(*register_producer(project or payload.get('project',''), payload, root=repo_root))


def _run_status_route(project, query, method, body, repo_root):
    if method != "GET" or not project:
        return _json(400, {"error": "GET /research/run/status?project=&id= required"})
    return _json(*research_runs.run_status_read(project, _q1(query, "id"), repo_root))


def _original_request_query(query,shape):
    if set(query)!={'project','request'}:raise ValueError('query')
    fields={}
    for key,items in query.items():
        items=[items] if isinstance(items,str) else items
        if not isinstance(items,(list,tuple)) or len(items)!=1 or not isinstance(items[0],str):raise ValueError('query')
        fields[key]=items[0]
    if not fields['project'].strip():raise ValueError('project')
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('duplicate JSON field')
            value[key]=item
        return value
    request=json.loads(fields['request'],object_pairs_hook=unique)
    from jsonschema import Draft202012Validator
    if next(Draft202012Validator(shape).iter_errors(request),None):raise ValueError('shape')
    return fields['project'],request


def _run_request_route(project, query, method, body, repo_root):
    """Pure exact original launch read; no launch, replacement or status guessing."""
    if method != 'GET':return _json(405, {'error':'GET /research/run/request only'})
    from laplace.writing.schemas import SCHEMAS
    try:project,request=_original_request_query(query,SCHEMAS['run_status']['oneOf'][1]['properties']['request'])
    except (ValueError,TypeError):
        return _json(422,{'error':'Research request read requires one project and one exact closed original launch with request_id.'})
    return _json(200,research_runs.inspect_request(project,request,repo_root))


def _record_request_route(project, query, method, body, repo_root):
    """Same canonical record/history custody; never a Save or fresh guard."""
    if method != 'GET':return _json(405,{'error':'GET /research/record/request only'})
    from laplace.research import research_records
    try:project,request=_original_request_query(query,research_records.record_request_contract())
    except (ValueError,TypeError):
        return _json(422,{'error':'Research record request read requires one project and one exact canonical original wrapper with request_id.'})
    return _json(200,research_records.inspect_request(project,request,repo_root))


def _cancel_route(project, query, method, body, repo_root):
    if method!='POST': return _json(405,{'error':'POST only'})
    try: payload=json.loads(body or b'{}')
    except ValueError:return _json(400,{'error':'bad json'})
    return _json(*research_runs.cancel(project or payload.get('project',''), payload,
                                       Path(repo_root) if repo_root else _repo_root()))


def _artifact_route(project, query, method, body, repo_root):
    return research_artifact_read.read(project, query, method, repo_root)


_ROUTES = {"/research/state": _state_route, "/research/result": _result_route,
           "/research/reconcile": _reconcile_route, "/research/record": _record_route, "/research/record/request": _record_request_route,
           "/research/run": _run_route, "/research/producer": _producer_route,
           "/research/run/status": _run_status_route, "/research/run/request": _run_request_route, "/research/cancel": _cancel_route,
           "/research/artifact": _artifact_route}

# ---- the compatibility facade: every old name, the owner's same object -------------------------

from laplace.research.research_context import repo_root as _repo_root



from laplace.research.research_records import record, reconcile

from laplace.research.research_runs import register_producer, launch


