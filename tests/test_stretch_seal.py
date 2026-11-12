"""THE STRETCH SEAL CLAUSE — 'incremental build' is structurally impossible to declare done.

The chrome census (census_verdicts.json) lets a surface survive mid-stretch as
``kept-unwired`` with an owning wave — that is the rebuild-then-kill sequencing,
not a licence. This clause is the terminal gate (DESIGN_2026-07-15_the-visual-
conception.md §6.4): at the STRETCH seal, zero kept-unwired rows may remain —
every enumerated route/control is either kept-wired to a live mechanism or
killed and gone. Run it with LAPLACE_STRETCH_SEAL=1 at the final seal (and at
any moment you want the honest distance-from-done count: run it un-gated via
``pytest tests/test_stretch_seal.py -q`` and read the skip message).

TWO teeth (A4): the kept-unwired count is only HALF the distance. A deferred-kill
row (guide/tutorial, killed but owning a later wave) is STILL ALIVE now — a
killed page still serving 200, a killed control's surface still on disk. At the
seal EVERY killed row must be PROVABLY GONE too: killed routes answer 404/410 on
a live server, killed surface files are absent. The un-gated skip message reports
BOTH counts (kept-unwired remaining AND killed-still-alive) so the distance is honest.
"""
from __future__ import annotations

import http.client
import importlib.util
import json
import os
import threading
from collections import Counter
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src" / "laplace"
_STORE = _SRC / "pipeline" / "census_verdicts.json"


def _rows() -> list[dict]:
    return json.loads(_STORE.read_text(encoding="utf-8"))["rows"]


def _load_census_module():
    spec = importlib.util.spec_from_file_location(
        "chrome_census", _REPO / "scripts" / "chrome_census.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _census_routes() -> set[str]:
    return {r["path"] for r in _load_census_module().census()["routes"]}


def _killed_alive_serverfree(killed: list[dict], census_routes: set[str]) -> list[str]:
    """A server-free 'still alive' estimate for the distance count: a killed row whose
    backing chrome is still on the live tree — a killed ROUTE still enumerable in the
    census, or a killed SURFACE / killed CONTROL whose file is still on disk. (The GATED
    clause below uses the authoritative live-server 404/410 check.)"""
    alive: list[str] = []
    for r in killed:
        kind = r["kind"]
        if kind == "route" and r["id"] in census_routes:
            alive.append(r["id"])
        elif kind == "surface" and (_SRC / r["id"]).exists():
            alive.append(r["id"])
        elif kind == "control" and (_SRC / (r.get("surface") or "")).exists():
            alive.append(r["id"])
    return alive


# ── live-server harness (the interface_weld / census idiom) ──────────────────

def _spin_server():
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _status(port: int, path: str) -> int:
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        c.request("GET", path)
        return c.getresponse().status
    finally:
        c.close()


def test_stretch_seal_zero_unwired_chrome():
    rows = _rows()
    unwired = [r for r in rows if r["verdict"] == "kept-unwired"]
    by_wave = Counter(r.get("owning_wave") or "?" for r in unwired)
    if os.environ.get("LAPLACE_STRETCH_SEAL") != "1":
        killed = [r for r in rows if r["verdict"] == "killed"]
        still_alive = _killed_alive_serverfree(killed, _census_routes())
        pytest.skip(
            "stretch-seal gate (set LAPLACE_STRETCH_SEAL=1 at the final seal) - "
            f"distance from done: {len(unwired)} kept-unwired rows remain, by wave: "
            + (", ".join(f"{w}:{n}" for w, n in sorted(by_wave.items())) or "none")
            + f"; and {len(still_alive)} killed-but-still-alive rows remain "
            f"(of {len(killed)} killed)"
        )
    assert not unwired, (
        "THE STRETCH DOES NOT SEAL: kept-unwired chrome remains (wire it or kill it "
        f"in its owning wave): {[(r['id'], r.get('owning_wave')) for r in unwired][:20]}"
        f" ... by wave: {dict(by_wave)}"
    )


def test_stretch_seal_every_killed_row_is_provably_gone():
    """The deferred-kill teeth (A4): at the seal, EVERY killed row is provably gone — a
    killed route answers 404/410 on a live make_handler() server, a killed surface (and a
    killed control's own surface) file is absent. Un-gated it skips, reporting the
    killed-still-alive distance by owning wave (the un-gated skip in the sibling clause
    reports both counts together)."""
    rows = _rows()
    killed = [r for r in rows if r["verdict"] == "killed"]
    if os.environ.get("LAPLACE_STRETCH_SEAL") != "1":
        still_alive = _killed_alive_serverfree(killed, _census_routes())
        by_wave = Counter(r.get("owning_wave") or "?"
                          for r in killed if r["id"] in set(still_alive))
        pytest.skip(
            "stretch-seal gate (set LAPLACE_STRETCH_SEAL=1 at the final seal) - "
            f"killed-but-still-alive: {len(still_alive)} of {len(killed)} killed rows are "
            "still on the live tree, by owning wave: "
            + (", ".join(f"{w}:{n}" for w, n in sorted(by_wave.items())) or "none")
        )
    # GATED: the live server is authority — every killed row must be gone for real.
    httpd = _spin_server()
    port = httpd.server_address[1]
    alive: list[tuple] = []
    try:
        for r in killed:
            kind = r["kind"]
            if kind == "route":
                st = _status(port, r["id"])
                if st not in (404, 410):
                    alive.append((r["id"], f"route answered {st}, want 404/410"))
            elif kind == "surface":
                if (_SRC / r["id"]).exists():
                    alive.append((r["id"], "surface file still present"))
            elif kind == "control":
                surf = r.get("surface") or ""
                if surf and (_SRC / surf).exists():
                    alive.append((r["id"], f"surface {surf} still present"))
    finally:
        httpd.shutdown()
    assert not alive, (
        "THE STRETCH DOES NOT SEAL: killed chrome is still ALIVE — its owning wave must "
        "excise it (404/410 the route, delete the surface): "
        f"{alive[:20]} ... ({len(alive)} of {len(killed)} killed rows still alive)"
    )
