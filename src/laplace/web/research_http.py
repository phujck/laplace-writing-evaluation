"""The /research HTTP reply shapes (research family R1): one query reader and one JSON reply.

Shared by the HTTP entry (laplace.web.research_surface, the route table) and the one owner that serves a GET route
of its own (writing.research_artifact_read), so neither needs the other for a query value or a JSON body.
No route, parsing of a request body or project resolution lives here.
"""
from __future__ import annotations

import json
from typing import Any

JSON = "application/json; charset=utf-8"


def json_reply(status: int, value: Any) -> tuple[int, str, bytes]:
    return status, JSON, json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def q1(query: dict, key: str) -> str:
    value = query.get(key, "")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return value.strip() if isinstance(value, str) else ""
