"""Wave 0 · L5 — ONE PALETTE PER SERVED ROUTE + the two legacy retirements.

The RULING's seal bar #4 made mechanical: *a page that does not load hymn.css does
not ship*. This clause re-scopes the one-palette law from ``REBUILT_SURFACES``
(test_shared_model.py) to EVERY route scanner.py actually serves a page on — the
un-rostered legacy survivors (/map, /altitude, /analytics) were bound by nothing,
which is exactly how "half the pages have the wrong background" slipped the seal.

Derived, never hand-listed: the served-page set is the authored roster
(``shared_ui.views_roster`` — "every live surface appears"), each row confirmed a
live 200 ``text/html`` page in the real scanner. For each such page this asserts:

  1. it LINKS ``/shared/hymn.css`` (the one palette) — a future page shipping
     without it FAILS here;
  2. any private ``:root`` fallback it carries is BYTE-IDENTICAL to hymn's tokens
     (the drift-proof form: a fallback is lawful only when it equals hymn, so it
     cannot fork the palette page-to-page).

And the two Wave-0 route retirements (review_static, conceptric_editor2 — superseded
by /artefact, /conceptric) 301 to their successor CARRYING the selection query, the
``/dials → /pipeline`` precedent. The templates stay on disk (file removal is HIS
named call); after this wave no route serves them.

The teeth are proven below on planted violations in tmp files (never the repo), so
the day a new page ships without the palette the gate already bites.
"""
from __future__ import annotations

import http.client
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src" / "laplace"
_HYMN = _SRC / "web" / "static_shared" / "hymn.css"

_ROOT_RE = re.compile(r":root\s*\{([^}]*)\}", re.S)
_TOKEN_RE = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;]+?)\s*;")


def _norm(v: str) -> str:
    """Normalise a token value for the drift check: whitespace is not drift, a
    changed colour/value is. Collapse all whitespace so ``#0e1116`` ≠ ``#070912``
    still bites while a re-spaced font stack does not read as a fork."""
    return re.sub(r"\s+", "", v)


def _root_tokens(css: str) -> dict[str, str]:
    """Every ``--name: value`` declared in EVERY ``:root{}`` block of ``css``
    (later wins, mirroring the cascade), normalised."""
    out: dict[str, str] = {}
    for block in _ROOT_RE.findall(css):
        for name, val in _TOKEN_RE.findall(block):
            out[name] = _norm(val)
    return out


def _hymn_tokens() -> dict[str, str]:
    toks = _root_tokens(_HYMN.read_text(encoding="utf-8"))
    assert "bg" in toks and toks["bg"], "hymn.css lost its --bg token — the palette source is broken"
    return toks


# ── the derived served-page set (the authored roster, verified live) ──────────

# Served pages that carry NO nav row. ACT5 (shared_ui.py _VIEWS, 2026-07-21) ruled the
# brain-scanner MAP ROW off the roster (it is a view of the ENGINE, not a project's work),
# but the /map ROUTE keeps serving — so the L5 palette law must still cover it (the whole
# point of this file is EVERY served page wears the palette, roster row or not; /map was the
# original "bound by nothing" survivor). Re-added here as an off-nav served survivor so the
# enumeration does not silently drop it when it left the nav.
_OFF_NAV_SERVED = [
    {"id": "map", "title": "Map", "path": "/map", "group": "off-nav",
     "purpose": "the brain-scanner map — a served route with no nav row (ACT5)"},
]


# THE CLEAN-ROOM CLASS (his ruling 2026-08-10, DESIGN_2026-08-10_the-redline-walk.md
# §"The clean room"): a surface may be built as its own room — no shell chrome, no shared
# stylesheet, its own CSS — when the posture it serves cannot be built on top of the
# existing scaffolding. Such a surface CANNOT link hymn.css: that is the point of it.
#
# The exemption is DECLARED ON THE ROSTER ROW (`clean_room: True`), never hardcoded by id
# here — the one producer says which class a surface is in, and this file only reads it. A
# clean-room row is held to its own, equally mechanical law below
# (`test_clean_room_surfaces_carry_a_complete_palette_of_their_own`): it must carry a
# COMPLETE `:root` of its own and link no shared stylesheet at all. What is forbidden to
# every surface either way is HALF-wearing the shared palette — a private `--bg` beside a
# linked hymn.css, which is exactly the drift the L5 clause exists to stop.
def _roster_paths() -> list[dict]:
    from laplace.web import shared_ui
    return [v for v in shared_ui.views_roster()["views"] if not v.get("clean_room")] \
        + [dict(v) for v in _OFF_NAV_SERVED]


def _clean_room_paths() -> list[dict]:
    from laplace.web import shared_ui
    return [v for v in shared_ui.views_roster()["views"] if v.get("clean_room")]


# ── live-server harness (the interface_weld / chrome_census idiom) ────────────

@pytest.fixture(scope="module")
def server():
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def _get(port: int, path: str):
    """One GET, redirects NOT followed → (status, ctype, location, body-text)."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        c.request("GET", path)
        r = c.getresponse()
        body = r.read().decode("utf-8", "replace")
        return r.status, r.getheader("Content-Type"), r.getheader("Location"), body
    finally:
        c.close()


# ═══════════════════════════════════════════════════════════════════════════
# L5 — every served page wears the one palette
# ═══════════════════════════════════════════════════════════════════════════

def test_the_enumeration_covers_the_legacy_survivors():
    """The derived served-page set is the roster, and it ACTUALLY contains the three
    un-rostered legacy survivors the L5 fix targets (/map, /altitude, /analytics) — so
    a green below is real coverage, not a vacuous pass over an empty/degenerate set."""
    paths = {v["path"] for v in _roster_paths()}
    assert paths, "the authored roster is empty — the served-page set derived nothing"
    for must in ("/", "/map", "/altitude", "/analytics"):
        assert must in paths, f"the roster no longer serves {must!r} — L5 coverage regressed"


def test_every_served_route_links_the_one_palette(server):
    """Seal bar #4, mechanical: every roster page serves a real 200 text/html and LINKS
    /shared/hymn.css. A future page (or a survivor stripped of the link) FAILS here.

    A roster row that 301s to a LIVE successor is followed one hop to the page the user
    actually lands on (pipeline's row path /pipeline → /project, contract/tombstones.yaml:
    '/pipeline 301s HERE' — the Project cockpit page landed at /project, the row kept its
    /pipeline label). A 301→200 is a live door, and the palette must ride the landed page."""
    missing = []
    for v in _roster_paths():
        st, ctype, loc, body = _get(server, v["path"])
        if st in (301, 302) and loc:                      # follow one hop to the landed page
            st, ctype, _loc2, body = _get(server, loc)
        assert st == 200 and "text/html" in (ctype or ""), \
            f"roster page {v['id']} ({v['path']}) is not a live 200 html page: {st} {ctype}"
        if "/shared/hymn.css" not in body:
            missing.append((v["id"], v["path"]))
    assert not missing, f"served pages that do NOT link the one palette (L5): {missing}"


def test_every_served_root_fallback_is_byte_identical_to_hymn(server):
    """A served page's private :root fallback is lawful ONLY if byte-identical to hymn's
    tokens (the drift-proof form). For every token a page redeclares that hymn owns, the
    value must equal hymn's — so no page can fork --bg/--panel/etc. A rebuilt surface
    that carries NO :root (relies purely on hymn) trivially passes; a survivor's fallback
    must match. Drift (a private --bg:#070912) FAILS here."""
    hymn = _hymn_tokens()
    drift = []
    for v in _roster_paths():
        _st, _ct, _loc, body = _get(server, v["path"])
        for name, val in _root_tokens(body).items():
            if name in hymn and val != hymn[name]:
                drift.append((v["id"], f"--{name}", val, hymn[name]))
    assert not drift, f"served pages whose :root forks a hymn token (want == hymn value): {drift}"


def test_clean_room_surfaces_carry_a_complete_palette_of_their_own(server):
    """THE CLEAN-ROOM LAW, the other half of L5. A surface the roster declares
    ``clean_room`` does not link hymn.css — it cannot, and saying so is the ruling. What it
    MUST do instead is carry a COMPLETE palette of its own: every ``var(--token)`` it uses
    is declared in its own ``:root``, so nothing on it resolves to an empty string and
    nothing depends on a stylesheet it never loads. It must also link NO stylesheet at all
    (a clean room that pulls someone else's css is not one).

    A page that half-wears the shared palette — a private ``--bg`` beside a linked
    hymn.css — is forbidden to every surface, clean room or not, by the two checks above.
    """
    rows = _clean_room_paths()
    assert rows, "the clean-room class is declared by no roster row — this check is vacuous"
    faults = []
    for v in rows:
        st, ctype, _loc, body = _get(server, v["path"])
        if st != 200 or "text/html" not in (ctype or ""):
            faults.append((v["id"], "not a live html page", st, ctype))
            continue
        if "/shared/hymn.css" in body:
            faults.append((v["id"], "links hymn.css — then it is not a clean room", "", ""))
        if "<link" in body:
            faults.append((v["id"], "pulls a stylesheet", "", ""))
        own = set(_root_tokens(body))
        used = set(re.findall(r"var\(\s*--([A-Za-z0-9_-]+)", body))
        missing = sorted(used - own)
        if missing:
            faults.append((v["id"], "uses tokens it never declares", ", ".join(missing), ""))
    assert not faults, f"clean-room surfaces that do not carry their own palette: {faults}"


# ═══════════════════════════════════════════════════════════════════════════
# the two Wave-0 route retirements (301 → successor, selection carried)
# ═══════════════════════════════════════════════════════════════════════════

# retired route → (successor, the redirect's own status)
_RETIRED = {
    "/review_static": "/artefact",
    "/conceptric_editor2": "/conceptric",
}


def test_retired_routes_301_to_successor_carrying_the_query(server):
    """review_static + conceptric_editor2 are behaviorally killed: a 301 to the successor
    (/artefact, /conceptric), the /dials precedent, CARRYING the selection query so a
    corpus/node deep-link lands on the same paper on the surviving surface. Bare (no
    query) lands on the bare successor."""
    wrong = []
    for route, successor in _RETIRED.items():
        # bare: 301 → the bare successor
        st, _ct, loc, _b = _get(server, route)
        if st != 301:
            wrong.append((route, "bare-status", st, 301))
        if loc != successor:
            wrong.append((route, "bare-location", loc, successor))
        # with a selection: the query travels to the successor's same corpus/node params
        qs = "corpus=falqon&node=S1"
        st2, _ct2, loc2, _b2 = _get(server, f"{route}?{qs}")
        if st2 != 301:
            wrong.append((route, "query-status", st2, 301))
        if loc2 != f"{successor}?{qs}":
            wrong.append((route, "query-location", loc2, f"{successor}?{qs}"))
    assert not wrong, f"a retired route did not 301 to its successor with the query carried: {wrong}"


def test_retired_routes_serve_no_page(server):
    """After the retirement no route serves the legacy templates: the routes answer a
    small 301 stub, never the 40–100KB legacy page (unreachable through scanner.py)."""
    for route in _RETIRED:
        st, _ct, _loc, body = _get(server, route)
        assert st == 301, f"{route} still serves a page (status {st}) — the file is reachable"
        assert len(body) < 400, f"{route} served a full body ({len(body)}B), not a redirect stub"


def test_conceptric_editor2_removed_now_his_word_came():
    """conceptric_editor2.html is DELETED (WO-20260717-002125-exporter-port, his word
    PV-20260717T002125Z "Bank the port, then delete"): scripts/export_demo.py was ported
    off it onto the rebuilt conceptric surface (conceptric.html + conceptric-panes.mjs over
    store.mjs), tests green, THEN the tombstoned template was git-rm'd. The /conceptric_editor2
    route still 301s to /conceptric (above) — a redirect stub, never the file."""
    assert not (_SRC / "conceptric_editor2.html").exists(), \
        "conceptric_editor2.html is back — its exporter (export_demo) is ported to conceptric.html; " \
        "the template was deleted on his named word and must stay gone"


def test_review_static_removed_now_his_word_came():
    """review_static.html is DELETED (WO-20260717-002125-exporter-port, his word
    PV-20260717T002125Z "Bank the port, then delete" — BOTH templates): scripts/export_review.py
    was ported off it onto the rebuilt artefact surface (artefact.html + artefact-panes.mjs over
    store.mjs, pdf.js reader), the port RAN against a real manuscript and the bundle rendered
    through the current surface (self-contained: the fetch shim answers every /artefact/* +
    /shared/* + /review/* + /projection/* read from the sealed blob), tests green, THEN the
    tombstoned template was git-rm'd. The /review_static route still 301s to /artefact (above)
    — a redirect stub, never the file."""
    assert not (_SRC / "review_static.html").exists(), \
        "review_static.html is back — its exporter (export_review) is ported to the artefact " \
        "surface; the template was deleted on his named word and must stay gone"


# ═══════════════════════════════════════════════════════════════════════════
# the teeth — proven on planted violations in tmp files, never the repo
# ═══════════════════════════════════════════════════════════════════════════

def test_the_missing_palette_link_is_caught(tmp_path):
    """A planted page with NO hymn link is caught by the link detector."""
    bad = tmp_path / "no_palette.html"
    bad.write_text("<!doctype html><head><style>body{background:#123}</style></head>", encoding="utf-8")
    assert "/shared/hymn.css" not in bad.read_text(encoding="utf-8")


def test_a_forked_root_value_is_caught():
    """A planted :root that forks --bg is caught by the byte-identical check — proven
    against the real hymn tokens (a no-op check would pass this for the wrong reason)."""
    hymn = _hymn_tokens()
    # SUPERSEDED 2026-07-22 (his identity — DESIGN_LANGUAGE.md §1): the planted
    # matching token follows the new canon (--panel #111827) so exactly --bg drifts.
    forked = ":root{ --bg:#070912; --panel:#111827; }"     # --bg drifts, --panel matches
    toks = _root_tokens(forked)
    drift = {n: v for n, v in toks.items() if n in hymn and v != hymn[n]}
    assert set(drift) == {"bg"}, f"the drift check missed/over-caught a planted fork: {drift}"


def test_a_byte_identical_fallback_does_not_trip_the_check():
    """The exact hymn :root block, re-declared as a page fallback, is CLEAN — the check
    forbids drift, not the drift-proof fallback (a false positive would make the lawful
    standalone-sane fallback unusable)."""
    hymn_root = _HYMN.read_text(encoding="utf-8")
    m = _ROOT_RE.search(hymn_root)
    assert m, "could not read hymn's :root block"
    page = f"<style>:root{{{m.group(1)}}}</style>"
    hymn = _hymn_tokens()
    drift = {n: v for n, v in _root_tokens(page).items() if n in hymn and v != hymn[n]}
    assert not drift, f"a byte-identical fallback wrongly tripped the drift check: {drift}"
