"""THE CHROME CENSUS — the binding clause (front-end rewrite, Wave 0 packet 0.1).

``scripts/chrome_census.py`` MECHANICALLY enumerates the interface surface (every
server route + every authored control); ``src/laplace/pipeline/census_verdicts.json`` is the
verdict STORE (law 8: a store, not markdown) — one ruling per enumerated item plus the
W0-kill records. This suite welds the two so no chrome ever escapes a verdict and no
verdict ever lies about the tree:

  (a) COVERAGE — every enumerated route + control has a verdict row (no un-verdicted
      chrome); every verdict is one of the three; kept-wired names an endpoint->producer
      mechanism; killed/kept-unwired carry an owning_wave.
  (b) NO PHANTOMS — every row is either still enumerable on the live tree, OR it is a
      killed row owning W0 that is provably gone (route absent from the census / file
      absent). A killed-in-a-later-wave row (guide/tutorial, owning W1) is STILL present
      now, so it must remain enumerable.
  (c) W0 KILLS ARE GONE NOW — the recorded W0 kills answer 404 on a live server
      (the /manuscript/* routes) or are absent from disk (viewer_app.html).
  (d) KEPT SURFACES ANSWER 200 — every page route (the kept-wired demoted instruments
      among them) serves a real 200 page on a live make_handler() server; the retired
      stubs answer their ruled 301/410 (the interface_weld / W0.3 idiom, reused).
  (e) STORE TRACKS THE CENSUS — the enumerator is deterministic, and the store's live
      route/control rows are EXACTLY the census (a bijection minus the W0 kills), so
      adding chrome without a verdict fails (a), and stale verdicts fail (b)/(e).

The live-server harness is the interface_weld pattern (a real make_handler() over
loopback); the whole suite stays well under 60s (one module-scoped server, a bounded
set of GETs). Pure stdlib + the committed store — no browser, no network.
"""
from __future__ import annotations

import http.client
import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src" / "laplace"
_STORE = _SRC / "pipeline" / "census_verdicts.json"
_WAVES = {f"W{i}" for i in range(10)}

# the retired doors and their ruled answer (W0.3 + W3), verbatim from test_interface_weld.
# W3 inverted the conceptric redirect: /conceptric is now THE page, /conceptric2 the 301 stub.
_RETIRED = {
    "/navigator": (301, "/altitude"),
    "/conceptric2": (301, "/conceptric"),
    "/editor": (410, None),
}


def _load_census_module():
    spec = importlib.util.spec_from_file_location(
        "chrome_census", _REPO / "scripts" / "chrome_census.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_CENSUS_MOD = _load_census_module()
_C = _CENSUS_MOD.census()
_STORE_OBJ = json.loads(_STORE.read_text(encoding="utf-8"))
_ROWS = _STORE_OBJ["rows"]
_BYKEY = {(r["kind"], r["id"]): r for r in _ROWS}

_CENSUS_ROUTES = {r["path"] for r in _C["routes"]}
_CENSUS_CONTROLS = {x["id"] for x in _C["controls"]}


# ── live-server harness (the interface_weld idiom) ───────────────────────────

@pytest.fixture(scope="module")
def server():
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def _get(port: int, path: str):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        c.request("GET", path)
        r = c.getresponse()
        body = r.read()
        return r.status, r.getheader("Location"), body
    finally:
        c.close()


# ── (a) COVERAGE ─────────────────────────────────────────────────────────────

def test_a_every_enumerated_route_and_control_has_a_verdict():
    missing_routes = sorted(p for p in _CENSUS_ROUTES if ("route", p) not in _BYKEY)
    missing_controls = sorted(x for x in _CENSUS_CONTROLS if ("control", x) not in _BYKEY)
    assert not missing_routes, f"un-verdicted routes (add a census_verdicts row): {missing_routes}"
    assert not missing_controls, f"un-verdicted controls (add a census_verdicts row): {missing_controls}"


def test_a_every_row_is_a_well_formed_verdict():
    bad = []
    for r in _ROWS:
        if r["verdict"] not in ("kept-wired", "kept-unwired", "killed"):
            bad.append((r["id"], "verdict", r["verdict"]))
        if r["kind"] not in ("route", "control", "surface"):
            bad.append((r["id"], "kind", r["kind"]))
        if r["verdict"] == "kept-wired":
            if r["owning_wave"]:
                bad.append((r["id"], "kept-wired must not own a wave", r["owning_wave"]))
        else:  # kept-unwired / killed carry a wave
            if r["owning_wave"] not in _WAVES:
                bad.append((r["id"], "owning_wave", r["owning_wave"]))
    assert not bad, f"malformed verdict rows: {bad}"


def test_a_kept_wired_mechanism_names_endpoint_and_producing_file():
    """view=mechanism: every kept-wired row's mechanism names an endpoint AND a producing
    module (`... -> <module>.py`). A kept-wired row with an empty/opaque mechanism is the
    exact lie this store exists to forbid."""
    offenders = []
    for r in _ROWS:
        if r["verdict"] != "kept-wired":
            continue
        m = r["mechanism"]
        if "->" not in m or ".py" not in m or "/" not in m:
            offenders.append((r["id"], m))
    assert not offenders, f"kept-wired rows not naming endpoint -> producing file: {offenders}"


# ── (b) NO PHANTOMS ──────────────────────────────────────────────────────────

def _enumerable(r) -> bool:
    if r["kind"] == "route":
        return r["id"] in _CENSUS_ROUTES
    if r["kind"] == "control":
        return r["id"] in _CENSUS_CONTROLS
    return (_SRC / r["id"]).exists()          # kind == surface


def test_b_no_phantom_verdicts():
    phantom = []
    for r in _ROWS:
        gone_w0 = (r["verdict"] == "killed" and r["owning_wave"] == "W0")
        enumerable = _enumerable(r)
        if gone_w0 and enumerable:
            phantom.append((r["id"], "W0-killed but still enumerable"))
        if not gone_w0 and not enumerable:
            phantom.append((r["id"], f"{r['verdict']}/{r['owning_wave'] or '-'} but not enumerable"))
    assert not phantom, f"phantom verdicts (row not backed by the live tree): {phantom}"


# ── (c) W0 KILLS ARE GONE NOW ────────────────────────────────────────────────

def test_c_w0_kills_are_gone_now(server):
    w0 = [r for r in _ROWS if r["verdict"] == "killed" and r["owning_wave"] == "W0"]
    assert len(w0) == 5, f"expected exactly the packet's 5 W0 kills, got {len(w0)}: {[r['id'] for r in w0]}"
    problems = []
    for r in w0:
        probe = r["probe"]
        if probe == "kill-404":
            st, _loc, _b = _get(server, r["id"])
            if st != 404:
                problems.append((r["id"], "want 404", st))
        elif probe.startswith("absent-file:"):
            rel = probe.split(":", 1)[1]
            if (_REPO / rel).exists():
                problems.append((r["id"], "file still present", rel))
        else:
            problems.append((r["id"], "unrecognised W0 probe", probe))
    assert not problems, f"a W0-killed item is not gone: {problems}"


def test_c_the_manuscript_family_and_viewer_orphan_are_the_kills():
    """The recorded W0 kills are exactly what this packet ruled: the four /manuscript/*
    bridge routes (zero live consumers; /editor already 410) and the viewer_app.html
    orphan surface (the standalone laplace.viewer server, superseded)."""
    killed = {r["id"] for r in _ROWS if r["verdict"] == "killed" and r["owning_wave"] == "W0"}
    assert killed == {
        "/manuscript/pdf", "/manuscript/conceptric",
        "/manuscript/provenance", "/manuscript/asset", "viewer_app.html",
    }, f"the W0 kill set drifted: {sorted(killed)}"
    # and the deletions really happened on disk / in scanner
    assert not (_SRC / "viewer_app.html").exists()
    assert not (_SRC / "viewer.py").exists()
    assert "/manuscript/pdf" not in _CENSUS_ROUTES


# ── (d) KEPT SURFACES ANSWER 200; RETIRED STUBS ANSWER THEIR RULING ──────────

def test_d_page_routes_serve_a_real_200(server):
    pages = [r for r in _ROWS if r.get("probe") == "page"]
    # W5: the /guide + /tutorial pages DIED and THE DESK COCKPIT (/desk) was born — net one
    # fewer page surface, so the roster is 10 page routes now (/, /map, /index.html,
    # /conceptric, /storyboard, /artefact, /desk, /dials, /analytics, /altitude).
    assert len(pages) >= 10, f"too few page routes to be the roster: {len(pages)}"
    # A killed page owns a LATER wave and is destined to 404 once that wave lands — requiring
    # it to 200 NOW would assert a killed page mechanically ALIVE (the census honesty hole A4
    # closes). The 200-liveness requirement is scoped to KEPT-* page routes only; a
    # killed-but-deferred page needs no liveness assertion (its deferred-kill teeth live in
    # the gated stretch-seal clause, not here).
    live_pages = [r for r in pages if r["verdict"] != "killed"]
    bad = []
    for r in live_pages:
        st, _loc, body = _get(server, r["id"])
        if st != 200 or len(body) < 200:
            bad.append((r["id"], st, len(body)))
    assert not bad, f"a kept page route did not serve a real 200: {bad}"
    # the KEPT-WIRED demoted instruments are among the 200-answering pages (clause d proper)
    wired_pages = {r["id"] for r in live_pages if r["verdict"] == "kept-wired"}
    assert {"/map", "/conceptric", "/altitude", "/analytics", "/index.html"} <= wired_pages, \
        f"a kept-wired demoted instrument is not a live 200 page: {wired_pages}"


def test_d_retired_stubs_answer_their_ruled_status(server):
    rows = {r["id"]: r for r in _ROWS}
    wrong = []
    for path, (want_st, want_loc) in _RETIRED.items():
        row = rows.get(path)
        assert row and row["verdict"] == "kept-wired" and row["probe"] == "redirect", \
            f"{path}: not recorded as a kept-wired retirement stub: {row}"
        st, loc, _b = _get(server, path)
        if st != want_st:
            wrong.append((path, "status", st, want_st))
        if want_loc is not None and loc != want_loc:
            wrong.append((path, "location", loc, want_loc))
    assert not wrong, f"a retired stub did not answer its ruled status: {wrong}"


# ── (e) STORE TRACKS THE CENSUS ──────────────────────────────────────────────

def test_e_census_is_deterministic():
    a = _CENSUS_MOD.census()
    b = _CENSUS_MOD.census()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True), \
        "the census enumerator is not deterministic across runs"


def test_e_store_live_rows_are_exactly_the_census():
    """The store's non-W0-killed route rows == the census routes, and its control rows ==
    the census controls (a bijection minus the W0 kills). Adding a route/control without a
    verdict fails (a); leaving a stale verdict for removed chrome fails here."""
    store_live_routes = {
        r["id"] for r in _ROWS
        if r["kind"] == "route" and not (r["verdict"] == "killed" and r["owning_wave"] == "W0")
    }
    store_controls = {r["id"] for r in _ROWS if r["kind"] == "control"}
    assert store_live_routes == _CENSUS_ROUTES, \
        f"route drift store<->census: {store_live_routes ^ _CENSUS_ROUTES}"
    assert store_controls == _CENSUS_CONTROLS, \
        f"control drift store<->census: {store_controls ^ _CENSUS_CONTROLS}"


def test_e_network_family_kept_wired_and_pinned():
    """/network/* is NOT a W0 orphan: it survives by the W0.3 ruling (pinned live by
    test_w0_3_retirements) — so every /network/* row is kept-wired, never killed."""
    net = [r for r in _ROWS if r["kind"] == "route" and r["id"].startswith("/network/")]
    assert net, "the /network/* family vanished from the store"
    assert all(r["verdict"] == "kept-wired" for r in net), \
        f"a /network/* row is not kept-wired: {[(r['id'], r['verdict']) for r in net]}"


# ── (f) PANE-SCANNED CONTROLS (F8 — the runtime control layer §C1 was blind to) ──
#
# The W5/W6/W7 rebuilt surfaces author ZERO control markup in their *.html; the whole
# interactive layer is rendered at runtime from static_shared/*-panes.mjs. The census
# now folds that pane-authored layer in (kind=control, probe='pane:<module>.mjs'), so
# the sealed "double-zero" is no longer blind to it. These clauses bind that fold.

_CENSUS_PANE_CONTROLS = {x["id"] for x in _C["controls"] if "pane" in x}
_STORE_PANE_ROWS = [r for r in _ROWS if str(r.get("probe", "")).startswith("pane:")]


def test_f_rebuilt_surfaces_have_pane_controls():
    """The three double-zero surfaces (desk/pipeline/assets) each now carry ≥1 control
    row — their runtime pane layer is enumerated, not invisible (F8 closes §C1)."""
    by_surface: dict[str, int] = {}
    for x in _C["controls"]:
        if "pane" in x:
            by_surface[x["surface"]] = by_surface.get(x["surface"], 0) + 1
    for surf in ("desk.html", "pipeline.html", "assets.html"):
        assert by_surface.get(surf, 0) >= 1, \
            f"{surf} has no pane-scanned control (the §C1 double-zero is still blind): {by_surface}"


def test_f_pane_controls_bijection_store_and_census():
    """The bijection EXTENDED TO PANES: every pane-scanned store row is a live census
    control and every pane-scanned census control has a store row (no phantom, no gap).
    Each pane row is a real control marked by its .mjs source."""
    store_ids = {r["id"] for r in _STORE_PANE_ROWS}
    assert store_ids == _CENSUS_PANE_CONTROLS, \
        f"pane control drift store<->census: {store_ids ^ _CENSUS_PANE_CONTROLS}"
    for r in _STORE_PANE_ROWS:
        assert r["kind"] == "control", (r["id"], "not a control row")
        assert r["probe"].endswith(".mjs"), (r["id"], r["probe"], "probe must name the .mjs source")


def test_f_desk_deferred_lifts_are_kept_unwired():
    """The KNOWN §C1 case made honest: the desk dream-lift verbs (authorize/refuse) are
    now ENUMERATED and ruled kept-unwired — the fail-closed 422 door (desk.py _DEFERRED_VERBS),
    deferred by design. This is exactly what turns the gated stretch-seal double-zero red."""
    byid = {r["id"]: r for r in _STORE_PANE_ROWS}
    for verb in ("authorize", "refuse"):
        rid = f"desk.html::desk-panes:verb:lifts.{verb}"
        assert rid in byid, f"the desk lifts.{verb} control is not enumerated"
        assert byid[rid]["verdict"] == "kept-unwired", (rid, byid[rid]["verdict"])
        assert byid[rid]["owning_wave"] in _WAVES, (rid, "kept-unwired needs an owning wave")
