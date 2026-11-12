"""tests/test_lineage_surface.py — the lineage surface's server composition (W-lineage).

The composed read models over the master node index + the descent walk + the provenance
door: the brief base altitude, node-outward, object-backward, the whole-graph regions, the
finder, the empty-state teach, the composed 404s, and the one write door. Driven against a
real scanner for the route contract; the composition is also asserted directly.

The reference paper is ``paper_falqon`` (91 concepts, 148 objects, 54/54 equations resolved
through the isnad rung, 26 honest absences, 2 figures on pages 6-7)."""
from __future__ import annotations

import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
CORPUS = "paper_falqon"


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
        body = r.read().decode("utf-8", "replace")
        return r.status, r.getheader("Content-Type"), body
    finally:
        c.close()


def _post(port: int, path: str):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        c.request("POST", path, b"{}", {"Content-Type": "application/json"})
        r = c.getresponse()
        body = r.read().decode("utf-8", "replace")
        return r.status, body
    finally:
        c.close()


# ── the page ────────────────────────────────────────────────────────────────
def test_the_page_serves_and_links_the_one_palette(server):
    st, ct, body = _get(server, "/lineage")
    assert st == 200 and "text/html" in (ct or "")
    assert "/shared/hymn.css" in body
    assert "lineage-panes.mjs" in body            # the surface rides its renderer
    assert "eng-brief" in body                    # the brief base altitude is the resting DOM


# ── the brief (base altitude): the real falqon numbers ────────────────────────
def test_brief_reads_the_real_falqon_health(server):
    st, ct, body = _get(server, f"/lineage/brief?corpus={CORPUS}")
    assert st == 200
    d = json.loads(body)
    assert d["present"] is True
    c = d["counts"]
    assert c["concepts"] == 91
    assert c["realised"] == 62
    assert c["rendered"] == 148
    assert c["resolved"] == 122
    assert c["equations"] == 54 and c["equations_resolved"] == 54
    assert c["unresolved"] == 26
    # the composed glance is prose carrying the real numbers, not a blob of ids.
    g = d["glance"]
    assert "91 concepts" in g and "148 rendered objects" in g and "unresolved" in g
    # the unresolved band is grouped by kind with a worded reason (absence stated).
    kinds = {b["kind"]: b["n"] for b in d["band"]}
    assert kinds == {"derivation": 13, "paragraph": 11, "figure": 2}
    assert all(b["reason"] for b in d["band"])
    # the staleness verdict + the named re-mint door ride the brief.
    assert d["staleness"] and d["remint"]["route"] == "POST /lineage/reindex"


# ── node-outward ──────────────────────────────────────────────────────────────
def test_node_outward_on_a_cluster_walks_its_descendants(server):
    st, ct, body = _get(server, f"/lineage/node?corpus={CORPUS}&node=cluster:claims")
    assert st == 200
    d = json.loads(body)
    assert d["present"] is True
    assert d["descendants"]["n"] == 22                       # the 22 claims
    assert d["identity"]["id"] == "cluster:claims"
    # the descendants tree carries relation-labelled edges (evidence one act deep).
    edges = d["descendants"]["edges"]
    assert edges and all(e.get("rel") for e in edges)
    assert d["descendants"]["tree"]["children"]
    # the crossings: an editor door and a Grow door, corpus-scoped, carrying the node.
    assert d["doors"]["editor"]["href"].startswith("/artefact?corpus=")
    assert "node=cluster%3Aclaims" in d["doors"]["grow"]["href"]


def test_node_outward_shows_the_objects_that_realise_a_concept(server):
    st, ct, body = _get(server, f"/lineage/node?corpus={CORPUS}&node=falqon_layers")
    assert st == 200
    d = json.loads(body)
    paras = d["realises"]["paragraphs"]
    assert len(paras) >= 1
    # each realising object carries its join provenance worded (not a bare id).
    assert all(p.get("provenance") for p in paras)


def test_node_outward_unknown_node_is_a_composed_404(server):
    st, ct, body = _get(server, f"/lineage/node?corpus={CORPUS}&node=nonesuch")
    assert st == 404
    d = json.loads(body)
    assert d["present"] is False
    assert "nonesuch" in d["glance"]                         # names what did not resolve


# ── object-backward ───────────────────────────────────────────────────────────
def test_object_backward_reaches_the_isnad_origin(server):
    st, ct, body = _get(server, f"/lineage/object?corpus={CORPUS}&object=eq:coh-total")
    assert st == 200
    d = json.loads(body)
    assert d["resolved"] is True
    assert d["join"] == "isnad"
    stages = [s["stage"] for s in d["steps"]]
    assert stages[0] == "object"
    assert "origin" in stages                                # walked back to its derivation origin
    origin = next(s for s in d["steps"] if s["stage"] == "origin")
    assert "coherent circuit volume" in (origin["label"] or "")


def test_object_backward_unknown_object_is_a_composed_404(server):
    st, ct, body = _get(server, f"/lineage/object?corpus={CORPUS}&object=zzz-not-a-thing")
    assert st == 404
    d = json.loads(body)
    assert d["resolved"] is False
    assert "zzz-not-a-thing" in d["glance"]


# ── the whole graph ───────────────────────────────────────────────────────────
def test_whole_graph_regions_and_the_unresolved_band(server):
    st, ct, body = _get(server, f"/lineage/whole?corpus={CORPUS}")
    assert st == 200
    d = json.loads(body)
    regions = d["regions"]
    assert regions and all("weight" in r and "weight_frac" in r for r in regions)
    # the unresolved objects are their own visible region (absence first-class).
    u = d["unresolved"]
    assert u["n"] == 26
    kinds = {g["kind"]: g["n"] for g in u["groups"]}
    assert kinds == {"derivation": 13, "paragraph": 11, "figure": 2}
    assert all(g["reason"] and g["sample"] for g in u["groups"])


# ── the finder ────────────────────────────────────────────────────────────────
def test_finder_lists_concepts_label_leading(server):
    st, ct, body = _get(server, f"/lineage/find?corpus={CORPUS}&q=claim")
    assert st == 200
    d = json.loads(body)
    assert d["concepts"]
    row = d["concepts"][0]
    assert "id" in row and "label" in row and "kind" in row


# ── the empty-state teach ─────────────────────────────────────────────────────
def test_empty_corpus_teaches_what_would_show(server):
    # qde is a registered conceptric project with no manuscript / index yet.
    st, ct, body = _get(server, "/lineage/brief?corpus=qde")
    assert st == 200
    d = json.loads(body)
    assert d["present"] is False
    assert d["empty"]["what_it_would_show"] and d["empty"]["what_builds_it"]


# ── the one write door + GET-only reads ───────────────────────────────────────
def test_reindex_gate_is_shut_under_pytest(server):
    """The one write door does NOT touch the live tree from a test run, and says so
    in its own words (503 + the read-only note) rather than borrowing the 404's
    "no manuscript resolves" — WO-20260817-test-mutates-working-tree."""
    from laplace.pipeline import derived_writes as dw
    st, body = _post(server, f"/lineage/reindex?corpus={CORPUS}")
    assert st == 503
    d = json.loads(body)
    assert d["minted"] is False and dw.WRITE_FLAG in d["error"]


def test_reindex_mints_the_index(server, monkeypatch):
    """The mint itself, opted into deliberately and restored byte-for-byte after."""
    from laplace.pipeline import derived_writes as dw, node_index as ni
    p = ni.index_path(CORPUS)
    before = p.read_bytes() if (p and p.is_file()) else None
    monkeypatch.setenv(dw.WRITE_FLAG, "1")
    try:
        st, body = _post(server, f"/lineage/reindex?corpus={CORPUS}")
        assert st == 200
        d = json.loads(body)
        assert d["minted"] is True and d["wrote"] == "node_index.json"
    finally:
        if before is not None:
            p.write_bytes(before)       # derived state: leave the tree as we found it


def test_reads_are_get_only(server):
    # a POST to a read route is refused (the reads never write).
    st, body = _post(server, f"/lineage/brief?corpus={CORPUS}")
    assert st == 405


# ── the surface is on the roster + the journey (reachable, covered) ───────────
def test_lineage_is_rostered_and_on_the_journey_once():
    from laplace.web import shared_ui as su
    roster = {v["id"] for v in su.views_roster()["views"]}
    assert "lineage" in roster
    seen = []
    for stg in su.journey_payload(None)["stages"]:
        seen.append(stg["view"])
        for door in stg["doors"]:
            if door.get("view"):
                seen.append(door["view"])
    assert seen.count("lineage") == 1                        # exactly once (the coverage law)
    assert "lineage" in seen
