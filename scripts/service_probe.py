"""The discovery seam: find the scanner/walk service, never assume it.

A probe that hardcodes ``http://127.0.0.1:8770`` and waits five seconds for it is
asserting a fact about the box it runs on. When the assertion is wrong the probe
does not learn that — it hangs, then grades the absence as a failure of the thing
it was pointed at. This module is the one place that answers "is the service
there, and where?", so every probe can ask instead of assume.

Resolution order (first hit wins):
  1. ``LAPLACE_WALK_URL`` in the environment — the explicit answer, honored as-is.
     A bare ``host:port`` or ``:port`` is normalized to an http URL.
  2. The known local default, ``http://127.0.0.1:8770`` (the serve-walk skill's
     local equivalent), probed with a sub-second connect.
  3. ``None`` — no service. Not an error, not a failure: an absence, named.

Stdlib only, by design: this runs BEFORE stand-up, on a box where the venv may not
exist yet, so it may not import playwright, requests, or laplace itself.

Use from a probe::

    from service_probe import resolve_service, REFUSAL_EXIT

    svc = resolve_service()
    if svc is None:
        print(refusal_line("SCROLL LAW", "the scanner", probed()))
        return REFUSAL_EXIT      # 3 — a refusal, never a graded fail

The companion helpers are deliberately blunt: :func:`refusal_line` writes the
absence in the same shape everywhere, so a caller reading stdout can tell a
refusal from a verdict without parsing.
"""
from __future__ import annotations

import os
import socket
import urllib.error
import urllib.parse
import urllib.request

#: The exit code that means REFUSED TO GRADE — the probe could not probe. It is
#: distinct from 0 (pass) and 1 (graded fail) on every script that uses it, so a
#: caller reading exit codes never mistakes an absence for a verdict. 2 is left
#: alone: several scripts already spend it on vacuous-walk / guard-violation.
REFUSAL_EXIT = 3

#: The known local default — the serve-walk skill's local equivalent
#: (``http://127.0.0.1:8770/walk?corpus=...``). Probed, never assumed.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8770

#: Sub-second by design. A TCP connect to a listening local socket completes in
#: microseconds; to a closed one it is refused immediately. The only case this
#: budget bounds is a firewalled/black-holed address, and there the right answer
#: is "absent" fast, not "maybe" slowly.
CONNECT_TIMEOUT = 0.4

#: The refusal sentence, in one place so every probe says the same thing.
REFUSAL_MEANING = ("a refusal is not a pass and not a graded fail: nothing was "
                   "measured, so nothing is graded, and no banked verdict or "
                   "evidence was written or overwritten")

#: The same sentence for a producer rather than a grader — a baker that refuses has no
#: verdict to withhold, only an artefact it did not write.
REFUSAL_MEANING_PRODUCE = ("a refusal is not a failure of the thing being built: nothing "
                           "was read, so nothing was built, and no existing output was "
                           "written or overwritten")


def normalize(url: str) -> str:
    """``8770`` / ``:8770`` / ``host:8770`` / ``http://host:8770/`` → an http base URL
    with no trailing slash. An explicit scheme is honored untouched."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return ""
    if "://" in u:
        return u
    if u.isdigit():
        return f"http://{DEFAULT_HOST}:{u}"
    if u.startswith(":"):
        return f"http://{DEFAULT_HOST}{u}"
    return "http://" + u


def _split(url: str) -> tuple[str, int]:
    p = urllib.parse.urlsplit(url)
    port = p.port or (443 if p.scheme == "https" else 80)
    return p.hostname or DEFAULT_HOST, port


def port_open(host: str, port: int, timeout: float = CONNECT_TIMEOUT) -> bool:
    """Is anything listening? A TCP connect, bounded, no HTTP round-trip — the
    cheapest honest answer to 'is the service there'."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def answers(url: str, path: str = "/corpus/list", timeout: float = 2.0) -> bool:
    """Does the thing listening actually speak the scanner's language? A listening
    socket is not a scanner (another app may hold the port), so the caller that
    needs the API — not just a host — asks this. Any HTTP response at all counts:
    a 404 still proves an HTTP server answered, and route sets differ per build."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + path, timeout=timeout) as r:
            r.read(1)
            return True
    except urllib.error.HTTPError:
        return True                     # answered, just not 200 — still a server
    except Exception:                   # noqa: BLE001 — absence is the answer
        return False


def probed() -> list[str]:
    """What resolution WOULD look at, in order, for the refusal line to name. Kept
    beside :func:`resolve_service` so the two can never drift apart."""
    env = os.environ.get("LAPLACE_WALK_URL", "").strip()
    out = [f"$LAPLACE_WALK_URL={normalize(env)}" if env
           else "$LAPLACE_WALK_URL (unset)"]
    out.append(f"http://{DEFAULT_HOST}:{DEFAULT_PORT} "
               f"(the known local default, {CONNECT_TIMEOUT}s connect)")
    return out


def resolve_service(*, require_api: bool = False) -> str | None:
    """The base URL of a live scanner/walk service, or ``None`` when there is none.

    ``require_api=True`` additionally demands that the listener answer an HTTP
    request (for probes that will call the API rather than just load a page).
    An explicit ``LAPLACE_WALK_URL`` is honored even when the probe cannot reach
    it — the author naming a URL is an instruction, not a hypothesis — EXCEPT
    that it is still reported absent if nothing is listening there, so a typo
    refuses instead of hanging.
    """
    env = os.environ.get("LAPLACE_WALK_URL", "").strip()
    if env:
        url = normalize(env)
        host, port = _split(url)
        if port_open(host, port) and (not require_api or answers(url)):
            return url
        return None
    url = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
    if port_open(DEFAULT_HOST, DEFAULT_PORT) and (not require_api or answers(url)):
        return url
    return None


def refusal_line(probe_name: str, absent: str, tried: list[str] | None = None,
                 verb: str = "GRADE") -> str:
    """The one refusal shape. ``probe_name`` is the gate ('SCROLL LAW'), ``absent``
    names what was missing ('the scanner on 127.0.0.1:8770', 'node on PATH'). ``verb``
    is what this script refuses to do — 'GRADE' for a probe, 'BAKE'/'BUILD' for a
    producer, which also swaps in the producer's wording of what a refusal means."""
    head = f"{probe_name}: REFUSED TO {verb} - {absent} is absent."
    meaning = REFUSAL_MEANING if verb == "GRADE" else REFUSAL_MEANING_PRODUCE
    body = "  " + meaning + "."
    if tried:
        body += "\n  probed: " + "; ".join(tried)
    return head + "\n" + body


def _cli() -> int:
    """``python3 scripts/service_probe.py`` — print what resolution finds, so a
    human or a stand-up script can ask the same question the probes ask."""
    svc = resolve_service()
    for line in probed():
        print("  probed: " + line)
    if svc is None:
        print("service: ABSENT (no scanner/walk base URL resolved)")
        return REFUSAL_EXIT
    print("service: " + svc + ("  (answers the API)" if answers(svc) else
                               "  (listening; did not answer /corpus/list)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
