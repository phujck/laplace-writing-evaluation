"""THE WALK-ONLY SERVING CONTRACT, driven through the real handler.

The gate (``laplace.manuscript.walk.gate_request``, enforced once in the scanner's ``parse_request``)
narrows the whole engine to the redline walk when ``LAPLACE_WALK_ONLY`` is set, and demands
a token alongside it when ``LAPLACE_WALK_TOKEN`` is. These tests drive the SCANNER'S OWN
handler class in-process — a real ``HTTPServer`` on an ephemeral loopback port, real request
lines, real status codes — because a gate graded by calling its predicate is graded on the
half of it that was never the risk. The risk is a route that reaches its branch anyway.

Every test restores the environment it touched and re-reads the gate's cached config, so the
default (gate OFF, the whole engine served) is what the rest of the suite sees.
"""
from __future__ import annotations

import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from laplace.web import scanner  # noqa: E402
from laplace.manuscript import walk


class _Server:
    """A scanner handler bound to an ephemeral loopback port, served on one thread."""

    def __init__(self) -> None:
        self.httpd = HTTPServer(("127.0.0.1", 0), scanner.make_handler())
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def get(self, path: str, headers: dict | None = None) -> tuple[int, str, dict]:
        """``(status, body_text, response_headers)`` — an error status is a RESULT here,
        never an exception, because the refusal's words are half of what is under test."""
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                     headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace"), dict(exc.headers)

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


@pytest.fixture()
def gate(monkeypatch):
    """Set the gate's environment and refresh its once-per-process read; the teardown puts
    the cached config back to whatever the ambient environment says."""
    def _set(**env):
        for k, v in env.items():
            if v is None:
                monkeypatch.delenv(k, raising=False)
            else:
                monkeypatch.setenv(k, v)
        walk.gate_config(refresh=True)
    yield _set
    monkeypatch.undo()
    walk.gate_config(refresh=True)


@pytest.fixture()
def server():
    s = _Server()
    yield s
    s.close()


# ── the mode itself ──────────────────────────────────────────────────────────────────────

def test_gate_off_by_default_changes_nothing(gate, server):
    """No env, no gate: /desk is served exactly as it was before the gate existed."""
    gate(LAPLACE_WALK_ONLY=None, LAPLACE_WALK_TOKEN=None)
    assert walk.gate_request("/desk", None) == {"refusal": None, "set_cookie": ""}
    status, _body, _h = server.get("/desk")
    assert status != 403, "the gate is off; nothing may be refused for being off-roster"


def test_gated_mode_serves_the_walk(gate, server):
    gate(LAPLACE_WALK_ONLY="1", LAPLACE_WALK_TOKEN=None)
    status, body, _h = server.get("/walk")
    assert status == 200
    assert "walk:corpus" in body, "the walk's own page, not some other surface's"


def test_gated_mode_refuses_the_desk_in_words(gate, server):
    gate(LAPLACE_WALK_ONLY="1", LAPLACE_WALK_TOKEN=None)
    status, body, headers = server.get("/desk")
    assert status == 403
    assert headers.get("Content-Type", "").startswith("text/plain")
    assert "/desk" in body and "redline walk only" in body
    assert "nothing was written" in body


@pytest.mark.parametrize("path", ["/walk", "/walk/doc", "/shared/walk.mjs",
                                  "/review/findings", "/projection/anything",
                                  "/artefact/context", "/favicon.ico"])
def test_every_route_the_contract_names_is_allowed(gate, path):
    gate(LAPLACE_WALK_ONLY="1", LAPLACE_WALK_TOKEN=None)
    assert walk.gate_allows(path), path
    assert walk.gate_request(path, None)["refusal"] is None


@pytest.mark.parametrize("path", ["/", "/desk", "/artefact", "/artefact/parity",
                                  "/pipeline", "/map", "/dials/op", "/review",
                                  "/storyboard"])
def test_every_other_route_is_refused(gate, path):
    gate(LAPLACE_WALK_ONLY="1", LAPLACE_WALK_TOKEN=None)
    assert not walk.gate_allows(path), path
    refusal = walk.gate_request(path, None)["refusal"]
    assert refusal is not None and refusal[0] == 403


def test_the_query_cannot_widen_the_path(gate):
    """The decision is the PATH's. A query that spells an allowed route does not make an
    off-roster path allowed, and one that spells a refused route does not close an open one."""
    gate(LAPLACE_WALK_ONLY="1", LAPLACE_WALK_TOKEN=None)
    assert walk.gate_request("/desk?next=/walk", None)["refusal"] is not None
    assert walk.gate_request("/walk?corpus=/desk", None)["refusal"] is None


# ── the token ────────────────────────────────────────────────────────────────────────────

def test_token_is_only_enforced_in_gated_mode(gate, server):
    """A token without the mode would read as a shut door on a server that is wide open."""
    gate(LAPLACE_WALK_ONLY=None, LAPLACE_WALK_TOKEN="s3cret")
    assert walk.gate_request("/walk", None) == {"refusal": None, "set_cookie": ""}
    status, _b, _h = server.get("/desk")
    assert status != 401


def test_wrong_token_is_401_in_words(gate, server):
    gate(LAPLACE_WALK_ONLY="1", LAPLACE_WALK_TOKEN="s3cret")
    status, body, headers = server.get("/walk?token=nope")
    assert status == 401
    assert headers.get("Content-Type", "").startswith("text/plain")
    assert "token" in body and "nothing was written" in body


def test_absent_token_is_401(gate, server):
    gate(LAPLACE_WALK_ONLY="1", LAPLACE_WALK_TOKEN="s3cret")
    status, _body, _h = server.get("/walk")
    assert status == 401


def test_right_token_in_the_query_serves_and_sets_the_cookie(gate, server):
    gate(LAPLACE_WALK_ONLY="1", LAPLACE_WALK_TOKEN="s3cret")
    status, body, headers = server.get("/walk?token=s3cret")
    assert status == 200
    assert "walk:corpus" in body
    assert walk.WALK_COOKIE in (headers.get("Set-Cookie") or ""), \
        "one authenticated request must carry the page's own fetches onward"


def test_right_token_as_a_bearer_serves(gate, server):
    gate(LAPLACE_WALK_ONLY="1", LAPLACE_WALK_TOKEN="s3cret")
    status, _body, _h = server.get("/walk",
                                   headers={"Authorization": "Bearer s3cret"})
    assert status == 200


def test_the_cookie_carries_the_token_on_later_requests(gate, server):
    gate(LAPLACE_WALK_ONLY="1", LAPLACE_WALK_TOKEN="s3cret")
    status, _b, _h = server.get("/shared/walk.mjs",
                                headers={"Cookie": f"{walk.WALK_COOKIE}=s3cret"})
    assert status == 200
    # …and a request that authenticated BY the cookie is not handed another one.
    assert walk.gate_request("/walk", _Headers({"Cookie": f"{walk.WALK_COOKIE}=s3cret"})) \
        == {"refusal": None, "set_cookie": ""}


def test_the_token_gate_still_refuses_an_off_roster_route(gate, server):
    """The path check runs FIRST: a valid token does not widen the served surface."""
    gate(LAPLACE_WALK_ONLY="1", LAPLACE_WALK_TOKEN="s3cret")
    status, body, _h = server.get("/desk?token=s3cret")
    assert status == 403
    assert "redline walk only" in body


class _Headers:
    """The smallest thing the gate asks of a headers object: ``.get(name)``."""

    def __init__(self, d: dict) -> None:
        self._d = d

    def get(self, name, default=""):
        return self._d.get(name, default)
