"""Tests for the brain scanner (N22) - the live conceptric viewer's backend.

The load-bearing invariants: a route result maps to the right node ids per
channel; the soul covenant holds in the self-graph (a soul node can light but
never carries content); the shard's inter-object edges resolve to real file
nodes; the firing ring is sequenced and persistent (so a fire from either of us
reaches both); and the HTTP surface serves graph + fire + poll end to end.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from laplace.engine import process_health, self_shard, telemetry
from laplace.web import scanner

# ---------------------------------------------------------------------------
# the route -> node-id mapping (pure, synthetic route)
# ---------------------------------------------------------------------------

def test_fired_from_route_maps_each_channel_to_a_node_id():
    route = {
        "canon": {
            "domain": "engine",
            "wiki": ["canon://workflow/earned_simplicity", "canon://operations/git_discipline"],
            "skills": ["earned_simplicity", "reconciler"],
        },
        "corpus": [{"key": "smith2020", "score": 3}],
        "self_knowledge": [{"file": "EIGEN_ARCHITECTURE.md", "section": "X", "score": 2}],
        "project": [{"file": "law-of-laws/HANDOFF.md", "section": "Y", "score": 1}],
        "soul": [{"ref": "soul/0007.md", "score": 4}],
    }
    fired = scanner._fired_from_route(route)
    ids = {f["id"]: f for f in fired}
    assert ids["wiki:workflow/earned_simplicity"]["channel"] == "canon.wiki"
    assert ids["wiki:workflow/earned_simplicity"]["rank"] == 1
    assert ids["skill:earned_simplicity"]["channel"] == "canon.skill"
    assert ids["ref:smith2020"]["channel"] == "corpus"
    assert ids["file:EIGEN_ARCHITECTURE.md"]["channel"] == "self_knowledge"
    assert ids["file:law-of-laws/HANDOFF.md"]["channel"] == "project"
    # soul lights, but is flagged sealed (never content)
    assert ids["file:soul/0007.md"]["channel"] == "soul"
    assert ids["file:soul/0007.md"]["sealed"] is True


# ---------------------------------------------------------------------------
# fire() against the real canon - structure + soul-refs-only + telemetry bank
# ---------------------------------------------------------------------------

@pytest.fixture()
def tiny_tree(tmp_path, monkeypatch):
    """A miniature repo so the shard side of fire()/_self_graph is fast + isolated.
    Canon routing still uses the real canon (independent of the repo root)."""
    (tmp_path / "src" / "laplace").mkdir(parents=True)
    (tmp_path / "src" / "laplace" / "alpha.py").write_text(
        '"""alpha module - the doorway."""\nfrom laplace.beta import thing\n\ndef open_door():\n    return thing\n',
        encoding="utf-8")
    (tmp_path / "src" / "laplace" / "beta.py").write_text(
        '"""beta module - the room."""\n', encoding="utf-8")
    (tmp_path / "NOTES.md").write_text(
        "# Notes\n\nSee [[alpha]] and [the room](src/laplace/beta.py).\n", encoding="utf-8")
    (tmp_path / "soul").mkdir()
    # the filename is public (you address/light a soul node by name); the CONTENT,
    # marked with a unique sentinel, is what the covenant must never expose.
    (tmp_path / "soul" / "0001.md").write_text(
        "# private\n\nSOULPAYLOAD_DO_NOT_LEAK - verbatim soul content.\n", encoding="utf-8")
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(self_shard, "_repo_root", lambda: tmp_path)   # the self graph's owner resolves its own root
    scanner._GRAPH_CACHE.clear()
    scanner._TREE_CACHE.clear()
    return tmp_path


def test_fire_lights_canon_and_keeps_soul_refs_only(tiny_tree):
    rec = scanner.fire("earned simplicity in the workflow", by="author")
    assert rec["by"] == "author"
    assert isinstance(rec["fired"], list) and rec["fired"]
    # the canon channel actually reached wiki/skill nodes
    assert any(f["id"].startswith("wiki:") for f in rec["fired"])
    ch = rec["channels"]
    assert "canon_wiki" in ch and "canon_skills" in ch and "shard" in ch
    # the soul covenant: every soul entry is a ref + score ONLY, never content
    for s in ch["soul"]:
        assert set(s.keys()) <= {"ref", "score"}


def test_fire_banks_to_telemetry_tagged_scanner(tiny_tree):
    telemetry.clear()
    scanner.fire("structure before minimisation", by="eigen")
    evs = [e for e in telemetry.events() if e.get("phase") == "reconstruction"]
    assert any(e.get("caller") == "scanner" for e in evs)


def test_fire_carries_kind_and_grade_for_eigen_reconstructions(tiny_tree):
    """N24: an Eigen reconstruction fire lights the EXPLICIT nodes it touched, tagged with the
    grade, so the author SEES Eigen fire through the grades - not just author goal-fires."""
    rec = scanner.fire("reconstruct self · grade 0", by="eigen", kind="reconstruct_self",
                       grade=0, nodes=["file:HANDOFF.md", "file:OPEN_STACK.md", "file:HANDOFF.md"])
    assert rec["by"] == "eigen" and rec["kind"] == "reconstruct_self" and rec["grade"] == 0
    # explicit nodes light in order, de-duplicated
    assert [f["id"] for f in rec["fired"]] == ["file:HANDOFF.md", "file:OPEN_STACK.md"]
    # a plain route fire keeps the old shape: kind=route, grade=None
    r2 = scanner.fire("earned simplicity", by="author")
    assert r2["kind"] == "route" and r2["grade"] is None
    # an unknown kind is normalised, not trusted
    r3 = scanner.fire("x", by="eigen", kind="evil", grade="nan", nodes=["file:HANDOFF.md"])
    assert r3["kind"] == "route" and r3["grade"] is None


# ---------------------------------------------------------------------------
# the self-graph - soul sealed, shard edges resolved to real file nodes
# ---------------------------------------------------------------------------

def test_self_graph_seals_soul_and_resolves_edges(tiny_tree):
    g = self_shard.self_graph()
    ids = {n["id"]: n for n in g["nodes"]}
    assert "file:src/laplace/alpha.py" in ids
    assert "file:src/laplace/beta.py" in ids
    assert "file:soul/0001.md" in ids

    # soul covenant: sealed, no content, no lines, distinct group
    soul = ids["file:soul/0001.md"]
    assert soul["kind"] == "soul" and soul["group"] == "soul"
    assert soul["meta"]["sealed"] is True
    assert "soulpayload" not in json.dumps(soul).lower()  # content never travels into the node
    assert soul["meta"]["lines"] == 0

    # every edge references real nodes; the python import + md path link resolved
    for e in g["edges"]:
        assert e["src"] in ids and e["dst"] in ids
    pairs = {(e["src"], e["dst"], e["rel"]) for e in g["edges"]}
    assert ("file:src/laplace/alpha.py", "file:src/laplace/beta.py", "import") in pairs
    assert ("file:NOTES.md", "file:src/laplace/beta.py", "link") in pairs


# ---------------------------------------------------------------------------
# the firing ring - sequenced, filtered by since, persistent across reloads
# ---------------------------------------------------------------------------

def test_firing_log_sequences_filters_and_persists():
    log = scanner._FiringLog()  # loads from the isolated (empty) state dir
    a = log.append({"goal": "a", "fired": []})
    b = log.append({"goal": "b", "fired": []})
    assert a["seq"] == 1 and b["seq"] == 2
    assert [r["goal"] for r in log.since(0)["firings"]] == ["a", "b"]
    assert [r["goal"] for r in log.since(1)["firings"]] == ["b"]
    assert log.since(2)["firings"] == []

    # a fresh log (a server restart) replays the persisted tail
    reloaded = scanner._FiringLog()
    assert [r["goal"] for r in reloaded.since(0)["firings"]] == ["a", "b"]


def test_unified_graph_merges_stores_collision_free():
    # the one conceptric: canon + self + corpus in one graph, each node tagged with
    # its store, ids unique across stores, no dangling placeholders, edges valid.
    g = scanner.graph_for("all", refresh=True)
    stores = {n.get("store") for n in g["nodes"]}
    assert "canon" in stores and "self" in stores
    ids = [n["id"] for n in g["nodes"]]
    assert len(ids) == len(set(ids))                       # no id collision across stores
    assert all(n["kind"] != "missing" for n in g["nodes"])  # dangling placeholders dropped
    present = set(ids)
    assert all(e["src"] in present and e["dst"] in present for e in g["edges"])
    # the soul still seals in the unified view
    for n in g["nodes"]:
        if n.get("group") == "soul":
            assert n["meta"]["sealed"] is True


def test_graph_for_caches_and_refreshes(tiny_tree):
    g1 = scanner.graph_for("self")
    g2 = scanner.graph_for("self")
    assert g1 is g2  # cached
    g3 = scanner.graph_for("self", refresh=True)
    assert g3 is not g1  # rebuilt


# ---------------------------------------------------------------------------
# descend - reconstruct any node grade by grade by RE-READING (not a stored copy)
# ---------------------------------------------------------------------------

def test_reconstruct_node_descends_by_reread(tiny_tree):
    r1 = scanner.reconstruct_node("file:src/laplace/alpha.py", grade=1)
    assert r1["reconstructible"] is True
    assert any("open_door" in s for s in r1["spine"])  # spine re-read from source
    assert r1["descend"]["to_grade"] == 2              # carries the call to the next grade
    r2 = scanner.reconstruct_node("file:src/laplace/alpha.py", grade=2)
    assert "alpha module" in r2["content"]             # content reconstructed by re-reading


def test_reconstruct_absent_source_is_honest_not_confident_wrong(tiny_tree):
    # the no-confident-wrong invariant: an unknown path must NOT reconstruct the
    # closest other file - it returns honest absence.
    r = scanner.reconstruct_node("file:src/laplace/does_not_exist.py", grade=1)
    assert r["reconstructible"] is False
    assert "name" not in r or r.get("name") != "src/laplace/does_not_exist.py"


def test_reconstruct_soul_is_sealed_at_every_grade(tiny_tree):
    for g in (1, 2):
        r = scanner.reconstruct_node("file:soul/0001.md", grade=g)
        assert r["sealed"] is True
        assert not r.get("content")
        assert "soulpayload" not in json.dumps(r).lower()


def test_reconstruct_canon_node_routes_through_the_one_reader():
    # a canon skill node reconstructs through the SAME graded reader as a file node,
    # by its repo path - one reconstruction, not one per source (self-similar).
    from laplace.pipeline.canon import get_canon
    name = next((n for n, sk in get_canon().skills.items()
                 if getattr(sk, "skill_md", None) and sk.skill_md.exists()), None)
    assert name, "expected at least one skill with a SKILL.md"
    r = scanner.reconstruct_node(f"skill:{name}", grade=1)
    assert r["reconstructible"] is True
    assert r["name"].endswith(".md")


# ---------------------------------------------------------------------------
# end to end over HTTP - the surface both of us hit
# ---------------------------------------------------------------------------

@pytest.fixture()
def live_server(tiny_tree, monkeypatch):
    scanner._FIRINGS = scanner._FiringLog()  # fresh, isolated firing ring
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def test_inflight_writing_post_is_visible_to_lifecycle_health(tiny_tree,monkeypatch):
    from laplace.web import project_work_surface
    entered=threading.Event();release=threading.Event();finished=[]
    def slow_handle(path,query,method,body=b"",repo_root=None):
        entered.set();assert release.wait(3)
        return 200,"application/json",b'{"ok":true}'
    monkeypatch.setattr(project_work_surface,"handle",slow_handle)
    httpd=ThreadingHTTPServer(("127.0.0.1",0),scanner.make_handler());port=httpd.server_address[1]
    server=threading.Thread(target=httpd.serve_forever,daemon=True);server.start()
    def post():
        req=urllib.request.Request(f"http://127.0.0.1:{port}/work/task",
            data=b'{"project":"fixture"}',method="POST",
            headers={"Content-Type":"application/json","X-Laplace-Writing":"1"})
        with urllib.request.urlopen(req,timeout=5) as response:finished.append(response.status)
    worker=threading.Thread(target=post);worker.start();assert entered.wait(2)
    health=_get(f"http://127.0.0.1:{port}/authoring/health")
    assert health["active_mutations"]==1
    assert any(row["kind"]=="http-mutation" and row["project"]=="fixture"
               and row["path"]=="/work/task" for row in health["active_work"])
    release.set();worker.join(5);assert finished==[200]
    assert _get(f"http://127.0.0.1:{port}/authoring/health")["active_mutations"]==0
    httpd.shutdown()


def test_exclusive_lifecycle_lock_drains_before_new_writing_post(tiny_tree,monkeypatch,tmp_path):
    import fcntl,time
    from laplace.web import project_work_surface
    state=tmp_path/"managed.json";monkeypatch.setenv("LAPLACE_WRITING_STATE",str(state))
    lock=(tmp_path/"managed.json.lock").open("a+");fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
    entered=threading.Event();release=threading.Event();finished=[]
    def slow_handle(path,query,method,body=b"",repo_root=None):
        entered.set();assert release.wait(3)
        return 200,"application/json",b'{"ok":true}'
    monkeypatch.setattr(project_work_surface,"handle",slow_handle)
    httpd=ThreadingHTTPServer(("127.0.0.1",0),scanner.make_handler());port=httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever,daemon=True).start()
    def post():
        req=urllib.request.Request(f"http://127.0.0.1:{port}/work/task",
            data=b'{"project":"fixture"}',method="POST",
            headers={"Content-Type":"application/json","X-Laplace-Writing":"1"})
        with urllib.request.urlopen(req,timeout=5) as response:finished.append(response.status)
    worker=threading.Thread(target=post);worker.start();time.sleep(.1)
    assert not entered.is_set(),"new mutation crossed the exclusive update drain"
    fcntl.flock(lock.fileno(),fcntl.LOCK_UN);lock.close()
    assert entered.wait(2)
    health=_get(f"http://127.0.0.1:{port}/authoring/health")
    assert health["active_mutations"]==1
    release.set();worker.join(5);assert finished==[200]
    httpd.shutdown()


def test_http_meta_graph_fire_and_poll(live_server):
    # /meta is RETIRED — 410 Gone (W5 chrome census kill: zero front-end consumers,
    # scanner.py do_GET "/meta" branch; the "all"/default-source concept it exposed now
    # rides graph_for's default). A retired assertion updated to assert the current ruled
    # truth: the route answers 410, never the old {sources, default} payload.
    with pytest.raises(urllib.error.HTTPError) as ei:
        _get(live_server + "/meta")
    assert ei.value.code == 410

    g = _get(live_server + "/graph?source=self")
    assert g["nodes"] and any(n["id"] == "file:src/laplace/alpha.py" for n in g["nodes"])
    # soul stays sealed over the wire
    for n in g["nodes"]:
        if n.get("group") == "soul":
            assert n["meta"]["sealed"] is True
            assert "soulpayload" not in json.dumps(n).lower()

    rec = _post(live_server + "/fire", {"goal": "earned simplicity", "by": "eigen"})
    assert rec["by"] == "eigen" and rec["seq"] == 1 and isinstance(rec["fired"], list)

    poll = _get(live_server + "/firings?since=0")
    assert poll["seq"] == 1 and len(poll["firings"]) == 1
    assert poll["firings"][0]["goal"] == "earned simplicity"
    assert _get(live_server + "/firings?since=1")["firings"] == []


def test_http_rejects_empty_goal(live_server):
    with pytest.raises(urllib.error.HTTPError) as ei:
        _post(live_server + "/fire", {"goal": "  ", "by": "author"})
    assert ei.value.code == 400


def test_client_fire_roundtrips_and_never_raises(live_server):
    """The client conjugate ``client_fire`` lets a long task - the soul pour - light a RUNNING
    scanner so the author watches the ingest. It round-trips against a live server and banks the
    fire; and it is NEVER on the pour's hot path: an empty goal or a dead port returns None, never
    raises, never blocks."""
    from urllib.parse import urlparse
    u = urlparse(live_server)
    rec = scanner.client_fire("earned simplicity", by="eigen", host=u.hostname, port=u.port)
    assert rec and rec["by"] == "eigen" and rec["goal"] == "earned simplicity"
    poll = _get(live_server + "/firings?since=0")
    assert any(f["goal"] == "earned simplicity" for f in poll["firings"])
    # robustness contract: a miss is silent, the pour proceeds untouched
    assert scanner.client_fire("   ", host=u.hostname, port=u.port) is None
    assert scanner.client_fire("anything", host="127.0.0.1", port=1, timeout=0.5) is None


# ---------------------------------------------------------------------------
# the graded tree (the keeper) - grades / growth pulse / the ring, all seal-safe
# ---------------------------------------------------------------------------

def test_pulse_fingerprints_the_tree(tiny_tree):
    # the Becoming lens' growth signal: a cheap file count + latest mtime, no graph build.
    p = scanner._pulse()
    assert p["files"] >= 4 and p["latest"] > 0   # alpha, beta, NOTES, soul/0001 at least


def test_grades_payload_seals_soul(tiny_tree):
    g = scanner.grades_payload(refresh=True)
    ids = {n["id"]: n for n in g["nodes"]}
    assert "soul/0001.md" in ids
    soul = ids["soul/0001.md"]
    assert soul["sealed"] is True and soul["essence"] == "" and soul["keywords"] == []
    assert "soulpayload" not in json.dumps(g).lower()         # content never travels the grade handle
    assert "by_grade" in g["stats"] and g["stats"]["max_grade"] >= 1


def test_ring_fire_returns_both_passes_and_holds_the_seal(tiny_tree):
    r = scanner.ring_fire("the room beta module", pull_fraction=0.0)
    assert r["via"] == "keeper-ring"
    assert isinstance(r["down"], list) and r["down"]            # the root is always visited
    assert isinstance(r["returns"], list) and r["returns"]      # at least one enriched return rises
    # the down-pass is grade-tagged; the return carries its grade + provenance leaves
    assert all("grade" in d and "id" in d for d in r["down"])
    assert all("grade" in x and "leaves" in x for x in r["returns"])
    # the covenant: a sealed return carries no result text, and no soul content travels anywhere
    for x in r["returns"]:
        if x["sealed"]:
            assert x["result"] == ""
    assert "soulpayload" not in json.dumps(r).lower()


def test_http_fire_accepts_kind_grade_and_nodes(live_server):
    """N24 over the wire: the POST surface Eigen's MCP tools ping carries kind/grade/nodes, and the
    record round-trips so the author's polling page can render the grade."""
    rec = _post(live_server + "/fire", {
        "goal": "reconstruct self · grade 1", "by": "eigen",
        "kind": "reconstruct_self", "grade": 1, "nodes": ["file:HANDOFF.md"],
    })
    assert rec["by"] == "eigen" and rec["kind"] == "reconstruct_self" and rec["grade"] == 1
    assert [f["id"] for f in rec["fired"]] == ["file:HANDOFF.md"]
    poll = _get(live_server + "/firings?since=0")["firings"]
    assert poll and poll[-1]["kind"] == "reconstruct_self" and poll[-1]["grade"] == 1


def test_http_pulse_grades_ring(live_server):
    """The lens surfaces over the wire: the growth pulse, the graded hierarchy (soul sealed),
    and the ring fire (down + enriched up), with the covenant held end to end."""
    p = _get(live_server + "/pulse")
    assert p["files"] >= 4 and p["latest"] > 0

    g = _get(live_server + "/grades?refresh=1")
    assert g["nodes"] and any(n["id"] == "soul/0001.md" and n["sealed"] for n in g["nodes"])
    assert "soulpayload" not in json.dumps(g).lower()

    r = _get(live_server + "/ring?goal=the%20room%20beta")
    assert r["via"] == "keeper-ring" and r["down"] and isinstance(r["returns"], list)
    assert "soulpayload" not in json.dumps(r).lower()

    with pytest.raises(urllib.error.HTTPError) as ei:
        _get(live_server + "/ring?goal=%20%20")
    assert ei.value.code == 400

# ---------------------------------------------------------------------------
# the rebuild diff - what LANDED (the weld made watchable)
# ---------------------------------------------------------------------------

def test_network_rebuild_diffs_what_landed(monkeypatch, tmp_path):
    """A refresh diffs the node sets: new ids surface as 'landed' entries (coarsest first),
    gone ids are named - so a fold's landing is seen, never hunted for. The baseline PERSISTS
    beside the tree, so a code-change restart no longer eats the landed card."""
    nets = [
        {"nodes": {"a": {"grade": 0}, "b": {"grade": 1}}, "reach": {}, "lenses": {}, "root": "a"},
        {"nodes": {"a": {"grade": 0}, "c": {"grade": 2}, "d": {"grade": 0}}, "reach": {}, "lenses": {}, "root": "a"},
        {"nodes": {"a": {"grade": 0}, "c": {"grade": 2}, "d": {"grade": 0}, "e": {"grade": 1}},
         "reach": {}, "lenses": {}, "root": "a"},
    ]
    calls = {"n": 0}

    def fake_load(_root):
        net = nets[min(calls["n"], len(nets) - 1)]
        calls["n"] += 1
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in net.items()}

    import laplace.engine.conceptric as conceptric
    monkeypatch.setattr(conceptric, "load_network", fake_load)
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)   # never the real repo's baseline
    scanner._NETWORK.clear()
    scanner._NETWORK_DIFF.clear()
    scanner._network()                       # first build - no prior set, no baseline, no diff
    assert scanner._NETWORK_DIFF == {}
    meta = scanner.network_meta(refresh=True)
    diff = meta["diff"]
    assert diff["n_new"] == 2 and diff["n_gone"] == 1
    assert [e["id"] for e in diff["new"]] == ["c", "d"]   # coarsest grade first
    assert diff["gone"] == ["b"]
    scanner._NETWORK.clear()                 # a process restart: memory gone, baseline on disk
    scanner._NETWORK_DIFF.clear()
    scanner._network()                       # the fresh process loads nets[2]; the baseline knows a,c,d
    assert [e["id"] for e in scanner._NETWORK_DIFF["new"]] == ["e"]   # the card survived the restart
    scanner._NETWORK.clear()
    scanner._NETWORK_DIFF.clear()


def test_warm_channel_probe_wake_bench_state(tmp_path, monkeypatch):
    """The frictionless rule: the recurring mechanical acts ride the warm process. probe() never
    raises on a git-less tree; bench gold is author-curated and scored against the REAL fire;
    cockpit state persists server-side (gitignored)."""
    import laplace.engine.conceptric as conceptric

    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(process_health, "_repo_root", lambda: tmp_path)   # the probe's owner resolves its own root
    # probe: a foreign (non-repo) root -> a LOUD verdict, no exception
    p = process_health.probe()
    assert "verdict" in p and isinstance(p["dirty"], int)
    assert p["probe_failed"] is True and p["verdict"].startswith("GIT PROBE FAILED")

    # bench: add gold, run it against a tiny fake net through the real fire_by_grade
    assert scanner.bench_add({"q": "", "expect": ""}).get("error")
    assert scanner.bench_add({"q": "find alpha", "expect": "a1", "kind": "recall"})["n"] == 1
    monkeypatch.setattr(conceptric, "load_network",
                        lambda _root: {"nodes": {
                            "root": {"grade": 1, "parent": None, "leaf": False,
                                     "members": ["a1"], "coverage": ["alpha"], "keywords": []},
                            "a1": {"grade": 0, "parent": "root", "leaf": True, "members": [],
                                   "coverage": [], "keywords": ["alpha", "find"]}},
                            "reach": {}, "lenses": {}, "root": "root"})
    scanner._NETWORK.clear()
    import laplace.representation.embed_router as embed_router
    monkeypatch.setattr(embed_router, "get_backend", lambda: None)   # lexical fallback path
    out = scanner.bench_run()
    assert out["n"] == 1 and out["rows"][0]["pass"] is True
    assert out["n_pass"] == 1

    # cockpit state: POST merges, GET returns, disk persists
    assert scanner.cockpit_state() == {}
    scanner.cockpit_state({"geo": {"beam": 5}, "panels": {"wake": True}})
    assert scanner.cockpit_state()["geo"]["beam"] == 5
    assert (tmp_path / scanner.COCKPIT_FILE).is_file()
    scanner._NETWORK.clear()
    scanner._NETWORK_DIFF.clear()


def _git_stub(monkeypatch, outcomes, default=(0, "", "")):
    """Stand in for ``subprocess.run`` inside ``probe()``: map a git argv to a result or an
    exception. Keys are the full command line (``"git status --porcelain"``); a value is either
    an Exception to raise or a ``(returncode, stdout, stderr)`` triple."""
    import subprocess

    class _Result:
        def __init__(self, rc, out, err):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def _run(cmd, **_kw):
        outcome = outcomes.get(" ".join(cmd), default)
        if isinstance(outcome, BaseException):
            raise outcome
        return _Result(*outcome)

    monkeypatch.setattr(subprocess, "run", _run)


_PROBE_KEYS = {"branch", "head", "last_commit", "dirty", "dirty_files", "verdict"}
_HEALTHY_GIT = {
    "git status --porcelain": (0, "", ""),
    "git rev-parse --show-toplevel": (0, str(scanner._repo_root()) + "\n", ""),
    "git rev-parse --abbrev-ref HEAD": (0, "main\n", ""),
    "git rev-parse --short HEAD": (0, "31967b7\n", ""),
    "git log -1 --pretty=%h %s": (0, "31967b7 the remote leg\n", ""),
}


def test_probe_never_reads_a_broken_git_as_a_clean_tree(monkeypatch):
    """The wake's verdict is what authorises skipping verification (F20 inherit-on-clean), so an
    unobtained git fact must not look like a benign one. Before the returncode check, a git that
    died - no git on PATH, a foreign root, a locked index, the timeout - made every call return
    "" and the probe announced "clean tree - inherit the banked green" over a tree it never saw.
    Each failure shape below must instead forbid inheriting and name its reason, and the dict must
    keep every key its consumers (wake.wake_payload) already read."""
    healthy = dict(_HEALTHY_GIT)

    # (a) no git at all: every call raises
    _git_stub(monkeypatch, {}, default=FileNotFoundError("No such file or directory: 'git'"))
    p = process_health.probe()
    assert p["probe_failed"] is True
    assert p["verdict"].startswith("GIT PROBE FAILED")
    assert "do NOT inherit the banked green" in p["verdict"]
    assert "clean tree" not in p["verdict"]
    assert "FileNotFoundError" in " ".join(p["probe_health"]["failures"])
    assert p["probe_health"]["ok"] is False
    # shape: the old keys, the old types - a consumer written against the clean probe still runs
    assert _PROBE_KEYS <= set(p)
    assert (p["branch"], p["head"], p["last_commit"]) == ("", "", "")
    assert p["dirty"] == 0 and p["dirty_files"] == []

    # (b) git runs and fails: nonzero rc, which the old code never read
    _git_stub(monkeypatch, {**healthy,
                            "git status --porcelain": (128, "", "fatal: not a git repository\n")})
    p = process_health.probe()
    assert p["probe_failed"] is True and p["verdict"].startswith("GIT PROBE FAILED")
    assert "rc=128" in p["verdict"] and "fatal: not a git repository" in p["verdict"]

    # (c) rc=0 but no fact: a live branch is never blank (detached prints the literal HEAD)
    _git_stub(monkeypatch, {**healthy, "git rev-parse --abbrev-ref HEAD": (0, "\n", "")})
    p = process_health.probe()
    assert p["probe_failed"] is True
    assert "empty branch" in " ".join(p["probe_health"]["failures"])


def test_probe_still_inherits_on_a_clean_tree_and_scopes_on_a_moved_one(monkeypatch):
    """The cure is on the failure path only: a git that answers keeps both live verdicts."""
    _git_stub(monkeypatch, dict(_HEALTHY_GIT))
    p = process_health.probe()
    assert p["probe_failed"] is False and p["probe_health"] == {"ok": True, "failures": []}
    assert p["verdict"].startswith("clean tree - no source delta")
    assert "runs no tests" in p["verdict"]
    assert (p["branch"], p["head"]) == ("main", "31967b7")
    assert p["last_commit"] == "31967b7 the remote leg"
    assert p["dirty"] == 0 and p["dirty_files"] == []

    _git_stub(monkeypatch, {**_HEALTHY_GIT,
                            "git status --porcelain": (0, " M src/laplace/web/scanner.py\n?? new.py\n",
                                                       "")})
    p = process_health.probe()
    assert p["probe_failed"] is False
    assert p["verdict"].startswith("tree moved - verify SCOPED")
    assert p["dirty"] == 2 and p["dirty_files"] == ["src/laplace/web/scanner.py", "new.py"]


def test_network_meta_serves_the_cockpit_vitals(tmp_path, monkeypatch):
    """The cockpit's vitals come FROM the mechanism (view-equals-mechanism): the standing
    reconstruction geometry is the engine's own constants (never a view-side copy), and the
    router health is read from the engine's own files (embedding cache, metric, proposal
    ledger)."""
    import json as _json

    import laplace.engine.conceptric as conceptric
    from laplace.representation import embed_router

    monkeypatch.setattr(conceptric, "load_network",
                        lambda _root: {"nodes": {"a": {"grade": 0}}, "reach": {},
                                       "lenses": {}, "root": "a"})
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    scanner._NETWORK.clear()
    scanner._NETWORK_DIFF.clear()
    (tmp_path / embed_router.CACHE_FILE).write_text(
        _json.dumps({"backend": "fastembed:test", "nodes": {"a": {"h": "x", "v": [0.1]}}}),
        encoding="utf-8")
    (tmp_path / embed_router.PROPOSALS_FILE).write_text('{"id":"a"}\n{"id":"b"}\n',
                                                        encoding="utf-8")
    meta = scanner.network_meta(refresh=True)
    g = meta["geometry"]
    assert g["beam"] == embed_router.BEAM
    assert g["per_branch_width"] == embed_router.PER_BRANCH_WIDTH
    assert g["path_decay"] == embed_router.PATH_DECAY
    assert g["ancestor_decay"] == conceptric.ANCESTOR_DECAY
    r = meta["router"]
    assert r["backend"] == "fastembed:test"
    assert r["embeddings_cached"] == 1
    assert r["proposals_banked"] == 2
    assert r["metric_trained"] is False
    scanner._NETWORK.clear()
    scanner._NETWORK_DIFF.clear()


def test_no_prewarm_switch_returns_before_all_prewarm_dependencies(monkeypatch):
    """The documented cold-tool switch must make prewarm literally no-work."""
    import builtins

    def unexpected(*_args, **_kwargs):
        pytest.fail("LAPLACE_NO_PREWARM invoked a prewarm dependency")

    real_import = builtins.__import__
    forbidden = {"front_door", "front_places", "embed_router"}

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "laplace" and forbidden.intersection(fromlist or ()):
            unexpected()
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setenv("LAPLACE_NO_PREWARM", "1")
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(scanner, "graph_for", unexpected)
    monkeypatch.setattr(scanner, "_network", unexpected)

    scanner._prewarm()


def test_test_process_serve_suppresses_broker_but_normal_serve_starts_it(monkeypatch):
    started: list[tuple[object, str | None]] = []

    class FakeServer:
        def __init__(self, *_args, **_kwargs):
            pass

        def serve_forever(self):
            pass

    class FakeThread:
        def __init__(self, *, target, name=None, daemon=None):
            self.target = target
            self.name = name

        def start(self):
            started.append((self.target, self.name))

    monkeypatch.setattr(scanner, "_EngineServer", FakeServer)
    monkeypatch.setattr(scanner.threading, "Thread", FakeThread)
    monkeypatch.setenv("LAPLACE_TEST_PROCESS", "1")

    scanner.serve(port=0)

    assert started == [(scanner._prewarm, None)]

    from laplace.web.conversation_serve import run_broker

    started.clear()
    monkeypatch.delenv("LAPLACE_TEST_PROCESS")
    scanner.serve(port=0)

    assert started == [
        (scanner._prewarm, None),
        (run_broker, "laplace-conversation-broker"),
    ]


def test_every_roster_view_resolves_to_a_live_route(live_server):
    """W0.1 fail-closed: every path in the ONE authored view-roster (GET
    /shared/views) resolves to a LIVE route - a roster row pointing at a 404 is
    the failure. Page routes serve their HTML regardless of corpus data, so this
    holds on the synthetic tree; the roster carries no /network/* data path (those
    rebuild the whole graph and are never nav destinations)."""

    def _status(path):
        req = urllib.request.Request(live_server + path,
                                     headers={"Accept": "text/html"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    # the endpoint returns the roster over the wire
    assert _status("/shared/views") == 200
    roster = _get(live_server + "/shared/views")["views"]
    assert roster

    for v in roster:
        code = _status(v["path"])
        assert code != 404, f"roster view {v['id']!r} points at a 404: {v['path']}"
        assert code == 200, f"roster view {v['id']!r} did not serve: {v['path']} -> {code}"


def test_traffic_view_counts_real_exchanges_and_keeps_its_own_reads_apart(tiny_tree):
    """C12 observation contract (residual R1/R2): the health door admits no query or exactly view=traffic against
    its declared schema; every other shape is refused 422 with the admitted reads BEFORE any health work and is not
    a diagnostic read; the live handler feeds the ledger at the socket; the view is never counted as normal traffic."""
    from laplace.web import traffic
    from laplace.web import authoring as authoring_surface
    calls=[];original=authoring_surface.handle
    def counting(path,*a,**k):
        if path=="/authoring/health":calls.append(path)
        return original(path,*a,**k)
    authoring_surface.handle=counting
    httpd=ThreadingHTTPServer(("127.0.0.1",0),scanner.make_handler());port=httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever,daemon=True).start()
    try:
        before=_get(f"http://127.0.0.1:{port}/authoring/health?view=traffic")
        assert before["schema_version"]=="laplace.writing-traffic/1"
        for _ in range(3):assert "schema_version" in _get(f"http://127.0.0.1:{port}/authoring/health")
        assert len(calls)==3
        for query in ("view=traffic&x=1","view=","view=traffic&view=traffic","other=1","view=health"):
            with pytest.raises(urllib.error.HTTPError) as refused:
                _get(f"http://127.0.0.1:{port}/authoring/health?{query}")
            body=json.loads(refused.value.read());assert refused.value.code==422,query
            assert [row["url"] for row in body["recovery"]]==["/authoring/health","/authoring/health?view=traffic"]
            assert body["help"]["payload"]=={"route":"/authoring/health","method":"GET"}
        assert len(calls)==3,"a refused selector does no health work"
        after=_get(f"http://127.0.0.1:{port}/authoring/health?view=traffic")
        health=after["routes"]["/authoring/health"]
        assert health["requests"]-before["routes"].get("/authoring/health",{"requests":0})["requests"]==8
        assert health["status"].get("4xx",0)>=5
        assert after["diagnostic"]["reads"]-before["diagnostic"]["reads"]==1,"only admitted view reads are self-reads"
        assert not any("view" in key or "?" in key for key in after["routes"])
    finally:
        httpd.shutdown();authoring_surface.handle=original
    traffic._reset_for_tests()


def test_the_traffic_view_refuses_a_non_loopback_client_and_is_declared(tiny_tree):
    """The declared health door: help names it, the route table routes it at its admission line, and a client that
    is not on loopback is refused 403 even with an allowed Host."""
    import io
    from laplace.native import declarations as d, verbs as writing_verbs
    detail=d.http_help("/authoring/health","GET")
    assert detail["operation"]=="authoring/health" and detail["input"]["properties"]["view"]["enum"]==["traffic"]
    assert detail["input"]["additionalProperties"] is False and d.http_lossless_query("/authoring/health","GET") is True
    assert any("loopback" in rule["says"] for rule in detail["rules"])
    assert writing_verbs.pairs_for("authoring/health")==(("read","project@project"),)
    site=writing_verbs.site_for("authoring/health");rel,_,line=site.rpartition(":")
    assert 'if u.path == "/authoring/health":' in (scanner.Path(rel).read_text().splitlines()[int(line)-1])
    Handler=scanner.make_handler();handler=Handler.__new__(Handler)
    handler.path="/authoring/health?view=traffic";handler.client_address=("192.0.2.7",5000);handler.headers={"Host":"localhost"}
    handler.request_version="HTTP/1.1";handler.command="GET";handler.requestline="GET /authoring/health?view=traffic HTTP/1.1";handler.wfile=io.BytesIO();handler._headers_buffer=[];handler._walk_cookie=""
    handler.do_GET()
    raw=handler.wfile.getvalue().decode();assert " 403 " in raw.split("\r\n",1)[0]
    assert json.loads(raw.split("\r\n\r\n",1)[1])["recovery"][1]["clients"]=="loopback"


def test_a_failing_traffic_observer_never_changes_a_response(tiny_tree, monkeypatch):
    """C12 residual R2: the observer is guarded at the scanner; its own failure is counted, the request is answered."""
    from laplace.web import traffic
    traffic._reset_for_tests()
    def broken(*a, **k):
        raise ValueError("observer fault")
    monkeypatch.setattr(traffic, "begin", broken)
    httpd=ThreadingHTTPServer(("127.0.0.1",0),scanner.make_handler());port=httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever,daemon=True).start()
    try:
        assert "schema_version" in _get(f"http://127.0.0.1:{port}/authoring/health")
        monkeypatch.undo()
        shot=_get(f"http://127.0.0.1:{port}/authoring/health?view=traffic")
        assert shot["observer_errors"]==1 and shot["unattributed"]["bytes_written"]>0
    finally:
        httpd.shutdown()
    traffic._reset_for_tests()
