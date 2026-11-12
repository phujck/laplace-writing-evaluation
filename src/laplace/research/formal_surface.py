"""HTTP-shaped formal verification surface; scanner owns routing."""
from __future__ import annotations

import json
import threading
from typing import Any

from laplace.pipeline import formal_verification as formal

_JSON = "application/json; charset=utf-8"
_ACTIVE_CHECKS = 0
_ACTIVE_LOCK = threading.Lock()


def active_checks() -> int:
    """Number of formal checks executing through the HTTP/tool surface now."""
    with _ACTIVE_LOCK:
        return _ACTIVE_CHECKS


def _begin_check() -> None:
    global _ACTIVE_CHECKS
    with _ACTIVE_LOCK:
        _ACTIVE_CHECKS += 1


def _end_check() -> None:
    global _ACTIVE_CHECKS
    with _ACTIVE_LOCK:
        _ACTIVE_CHECKS = max(0, _ACTIVE_CHECKS - 1)


def _q(query: dict, name: str) -> str:
    value = query.get(name, "")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


def _response(status: int, value: dict) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(value, ensure_ascii=False).encode("utf-8")


def handle(path: str, query: dict, method: str, body: bytes, repo_root=None) -> tuple[int, str, bytes] | None:
    if path != "/formal" and not path.startswith("/formal/"):
        return None
    method = method.upper()
    if path == '/formal/targets' and method == 'GET':
        try:
            return _response(200, formal.targets(_q(query, 'project'), repo_root if repo_root else None,
                node=_q(query, 'node'), offset=int(_q(query, 'offset') or 0), limit=int(_q(query, 'limit') or 40)))
        except ValueError as exc: return _response(422, {'error': str(exc)})
    if path == "/formal/state" and method == "GET":
        project = _q(query, "project")
        if not project:
            return _response(400, {"error": "project is required"})
        return _response(200, formal.state(project, repo_root=repo_root))
    if path == "/formal/check" and method == "POST":
        try:
            payload = json.loads(body or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("body must be an object")
            required = ("project", "file", "declaration") + (("concept_id", "concept_revision", "source_revision") if payload.get("concept_id") else ("result_id", "result_revision"))
            if any(not isinstance(payload.get(key), str) or not payload[key].strip() for key in required):
                raise ValueError("Missing required fields: " + ", ".join(required))
            _begin_check()
            try:
                result = formal.check(payload["project"], file=payload["file"], declaration=payload["declaration"],
                                      result_id=payload.get("result_id", ""), result_revision=payload.get("result_revision", ""),
                                      concept_id=payload.get('concept_id',''), concept_revision=payload.get('concept_revision',''),
                                      source_revision=payload.get('source_revision',''), repo_root=repo_root)
            finally:
                _end_check()
        except (ValueError, json.JSONDecodeError) as exc:
            return _response(422, {"error": str(exc)})
        status = 200 if result.get("proof_status") in {"CHECKED", "UNAVAILABLE", "REJECTED", "FAILED"} else 422
        return _response(status, result)
    return _response(405, {"error": f"{method} {path} is not supported"})
