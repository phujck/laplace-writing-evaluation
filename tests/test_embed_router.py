"""The embedding router, pinned: the fold-time cache (content-hashed, incremental, pruned),
the cosine-guided descent (level-pooled, leaves accumulate, salience min-maxed over the pull),
and the marked fallback (no model -> the lexical ring, and the view says so).

The HashBackend (deterministic char-3gram geometry) drives every test - no model, no network;
the open-weight model's behaviour is gated by the navigator's hello check, not by unit tests.

BUDGET-SENSITIVE (the third judge's datum, 2026-08-24): ~20 tests presume the serving drip
can embed, so firing this shard with LAPLACE_EMBED_BUDGET=0 exported reads ~20 false reds.
A test run is a BUILD act and takes the build's env - the judge's descent pin is for
descents, never for firing build shards (M-judges-pin-is-for-descents).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from laplace.engine import conceptric
from laplace.representation import embed_router
from laplace.representation.embed_router import CACHE_FILE, HashBackend


def _net():
    nodes = {
        "root": {"id": "root", "grade": 2, "parent": None, "leaf": False,
                 "members": ["A", "B"], "coverage": ["alpha", "banana"], "keywords": []},
        "A": {"id": "A", "grade": 1, "parent": "root", "leaf": False, "members": ["a1", "a2"],
              "coverage": ["alpha", "particle"], "keywords": ["alpha"],
              "essence": "the alpha cluster - particle physics notes"},
        "B": {"id": "B", "grade": 1, "parent": "root", "leaf": False, "members": ["b1"],
              "coverage": ["banana"], "keywords": ["banana"],
              "essence": "the banana cluster - bread recipes"},
        "a1": {"id": "a1", "grade": 0, "parent": "A", "leaf": True, "members": [],
               "coverage": [], "keywords": ["alpha", "particle"],
               "essence": "alpha particle physics scattering"},
        "a2": {"id": "a2", "grade": 0, "parent": "A", "leaf": True, "members": [],
               "coverage": [], "keywords": ["alpha", "decay"],
               "essence": "alpha decay chains"},
        "b1": {"id": "b1", "grade": 0, "parent": "B", "leaf": True, "members": [],
               "coverage": [], "keywords": ["banana", "bread"],
               "essence": "banana bread recipe with walnuts"},
    }
    reach = {nid: set() for nid in nodes}
    lenses = {k: ["engine"] for k in nodes}
    return {"nodes": nodes, "reach": reach, "lenses": lenses, "root": "root"}


# ---------------------------------------------------------------------------
# the test geometry - deterministic, unit-norm
# ---------------------------------------------------------------------------

def test_hash_backend_is_deterministic_and_unit():
    b = HashBackend()
    v1, v2 = b.embed(["alpha particle"])[0], b.embed(["alpha particle"])[0]
    assert v1 == v2
    assert sum(x * x for x in v1) == pytest.approx(1.0)
    assert b.query("alpha particle") == v1


# ---------------------------------------------------------------------------
# the fold-time cache - embed once, re-embed only what changed, prune the gone
# ---------------------------------------------------------------------------

def test_ensure_embeddings_is_incremental(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LAPLACE_EMBED_BUDGET", "100")
    net = _net()
    b = HashBackend()
    first = embed_router.ensure_embeddings(tmp_path, net, b)
    assert first["n_embedded"] == len(net["nodes"]) and first["n_cached"] == 0
    again = embed_router.ensure_embeddings(tmp_path, net, b)
    assert again["n_embedded"] == 0 and again["n_cached"] == len(net["nodes"])
    assert again["changed_ids"] == []
    # one node's handle changes -> exactly one re-embed
    net["nodes"]["b1"]["essence"] = "banana bread, now with chocolate"
    third = embed_router.ensure_embeddings(tmp_path, net, b)
    assert third["n_embedded"] == 1
    assert third["changed_ids"] == ["b1"]
    # a vanished node is pruned from the SERVED vectors immediately, but a prune-only
    # serving call does not rewrite the tracked cache (a serve that dirtied the tree
    # blocked every pull); the on-disk prune persists at the next bulk (producer) fold
    del net["nodes"]["a2"]
    net["nodes"]["A"]["members"] = ["a1"]
    fourth = embed_router.ensure_embeddings(tmp_path, net, b)
    assert "a2" not in fourth["vectors"]
    on_disk = json.loads((tmp_path / CACHE_FILE).read_text(encoding="utf-8"))
    assert "a2" in on_disk["nodes"]
    embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)
    on_disk = json.loads((tmp_path / CACHE_FILE).read_text(encoding="utf-8"))
    assert "a2" not in on_disk["nodes"]


# ---------------------------------------------------------------------------
# W6.2 banked-what-travels: the cache is stored int8-quantized so it TRAVELS
# under the 100MB wall, and BOTH loaders adopt the quantized form (and still
# load a legacy float cache) so a warm-arrival pull re-embeds nothing.
# ---------------------------------------------------------------------------

def test_cache_is_stored_int8_quantized(tmp_path: Path):
    """The on-disk cache is the int8 form: a format marker + per-node {h, q(base64), s(scale)},
    never the raw float list. This is the shrink that lets it cross the 100MB wall tracked."""
    net = _net()
    embed_router.ensure_embeddings(tmp_path, net, HashBackend(), bulk=True)
    disk = json.loads((tmp_path / CACHE_FILE).read_text(encoding="utf-8"))
    assert disk["format"] == embed_router.CACHE_FORMAT == "int8"
    for nid, ent in disk["nodes"].items():
        assert "v" not in ent, f"{nid} stored as raw floats — not quantized"
        assert set(ent) == {"h", "q", "s"} and isinstance(ent["q"], str)


def test_quantize_dequantize_round_trip_preserves_cosine():
    """int8 quantization is tolerable for the routing dot: the round-trip cosine of a real
    unit vector against itself stays >0.999 (the packet's fidelity floor)."""
    import numpy as np
    rng = np.random.default_rng(7)
    for _ in range(20):
        v = rng.standard_normal(384).astype("float32")
        v /= np.linalg.norm(v)
        ent = embed_router._quantize_vec(v.tolist())
        back = np.asarray(embed_router._dequantize_entry(ent), dtype="float32")
        cos = float(v @ back / (np.linalg.norm(v) * np.linalg.norm(back)))
        assert cos > 0.999, f"round-trip cosine {cos} below fidelity floor"


def _concept_net(cluster_id: str):
    """A residue leaf under a concept cluster - the shape meaning_upfold hands the net, where the
    cluster's id is a sha1 over its member leaf ids."""
    nodes = {
        "root": {"id": "root", "grade": 2, "parent": None, "leaf": False, "members": [cluster_id],
                 "coverage": [], "keywords": []},
        cluster_id: {"id": cluster_id, "grade": 1, "parent": "root", "leaf": False,
                     "kind": "concept", "members": ["notes/x.md"], "coverage": ["fold"],
                     "keywords": ["fold", "residue"], "essence": "fold residue upfold"},
        "notes/x.md": {"id": "notes/x.md", "grade": 0, "parent": cluster_id, "leaf": True,
                       "kind": "md", "members": [], "coverage": [], "keywords": ["fold"],
                       "essence": "a note about the fold"},
    }
    return {"nodes": nodes, "reach": {n: set() for n in nodes}, "lenses": {}, "root": "root"}


def test_a_concept_ancestor_puts_no_cluster_id_in_the_chain(tmp_path: Path):
    """C1a (WO-20260821-embed-rebuild-boundary): a cluster id is a sha1 over member ids, so naming it
    here tied every descendant's staleness to its ancestors' MEMBERSHIP. At the shipped
    CHAIN_LABEL_TERMS=0 the rung is dropped rather than relabelled - measured, see _ancestor_label."""
    net = _concept_net("concept::a1b2c3d4e5")
    txt = embed_router.node_text(tmp_path, net, "notes/x.md")
    assert "concept::a1b2c3d4e5" not in txt
    assert txt.split(" | ")[1] == "root"


def test_chain_label_terms_widens_the_concept_rung(tmp_path: Path, monkeypatch):
    """The dial: at N>0 the rung is the label's N most distinctive terms (meaning_upfold._label ranks
    them by tf*idf), and the walk still spends its three rungs on the same three ancestors."""
    monkeypatch.setattr(embed_router, "CHAIN_LABEL_TERMS", 2)
    net = _concept_net("concept::a1b2c3d4e5")
    assert embed_router.node_text(tmp_path, net, "notes/x.md").split(" | ")[1] == "root > fold residue"


def test_a_cluster_remint_no_longer_restales_its_descendants(tmp_path: Path):
    """The rebuild boundary, closed: re-minting the ancestor's id - what any membership change does -
    leaves the descendant's text, and so its content hash, byte-identical."""
    before = embed_router.node_text(tmp_path, _concept_net("concept::a1b2c3d4e5"), "notes/x.md")
    after = embed_router.node_text(tmp_path, _concept_net("concept::9f8e7d6c5b"), "notes/x.md")
    assert before == after


def test_a_non_concept_ancestor_still_contributes_its_id_tail(tmp_path: Path):
    """Directory and lens ancestors are unchanged: their tail is already a word and already stable,
    so the label rule must not reach them even when they carry an essence."""
    net = _net()
    assert embed_router.node_text(tmp_path, net, "a1").split(" | ")[1] == "root > A"


def test_loaders_adopt_a_legacy_float_cache_without_reembedding(tmp_path: Path):
    """A committed legacy ``{"v":[float,...]}`` cache (the pre-W6.2 form) is adopted in place:
    ensure_embeddings serves it with n_embedded==0 (no re-embed) and _frontier_vectors reads it
    too. This is the backward-compat that lets an old cache warm a pull before it re-quantizes."""
    net = _net()
    b = HashBackend()
    # hand-write a legacy float cache with the exact hashes the loader will compute
    texts = {nid: embed_router.node_text(tmp_path, net, nid) for nid in net["nodes"]}
    legacy = {nid: {"h": embed_router._hash(b.name, t), "v": b.embed([t])[0]}
              for nid, t in texts.items()}
    (tmp_path / CACHE_FILE).write_text(
        json.dumps({"backend": b.name, "nodes": legacy}), encoding="utf-8")
    rep = embed_router.ensure_embeddings(tmp_path, net, b)
    assert rep["n_embedded"] == 0 and rep["n_cached"] == len(net["nodes"])
    assert len(rep["vectors"]["a1"]) == b.dim              # dequant returned the float row
    fv = embed_router._frontier_vectors(tmp_path, net, b, {"a1", "b1"})
    assert set(fv) == {"a1", "b1"} and len(fv["a1"]) == b.dim


def test_serving_budget_defers_loudly_and_drips(tmp_path: Path, monkeypatch, capsys):
    """The PSU guard (2026-07-13, two Kernel-Power 41 hard crashes): a SERVING-path call
    (bulk=False, the scanner pre-warm / route) embeds at most LAPLACE_EMBED_BUDGET stale nodes
    per call, defers the rest LOUDLY (n_deferred + a printed line, never silent), and
    successive calls DRIP the cache toward fresh in deterministic order."""
    net = _net()
    b = HashBackend()
    monkeypatch.setenv("LAPLACE_EMBED_BUDGET", "2")
    n = len(net["nodes"])                                    # 6

    first = embed_router.ensure_embeddings(tmp_path, net, b)
    assert first["n_embedded"] == 2 and first["n_deferred"] == n - 2
    assert len(first["vectors"]) == 2
    assert "DEFERRED 4" in capsys.readouterr().out           # loud, not a log-swallowed shrug
    on_disk = json.loads((tmp_path / CACHE_FILE).read_text(encoding="utf-8"))
    # deterministic drip order, apex-first: the first budgeted call warms the root and the
    # id-earliest lens - not a lexicographic prefix (WO-20260820-graded-serving-drip)
    assert sorted(on_disk["nodes"]) == ["A", "root"]

    second = embed_router.ensure_embeddings(tmp_path, net, b)
    assert second["n_embedded"] == 2 and second["n_deferred"] == n - 4
    third = embed_router.ensure_embeddings(tmp_path, net, b)
    assert third["n_embedded"] == 2 and third["n_deferred"] == 0
    done = embed_router.ensure_embeddings(tmp_path, net, b)
    assert done["n_embedded"] == 0 and done["n_deferred"] == 0
    assert done["n_cached"] == n                              # converged, budget never spiked


def test_bulk_callers_ignore_the_budget(tmp_path: Path, monkeypatch):
    """bulk=True is the deliberate producer posture (metric_distill, the explicit CLI fold):
    the guard never throttles a caller that INTENDS the full fold."""
    monkeypatch.setenv("LAPLACE_EMBED_BUDGET", "2")
    net = _net()
    rep = embed_router.ensure_embeddings(tmp_path, net, HashBackend(), bulk=True)
    assert rep["n_embedded"] == len(net["nodes"]) and rep["n_deferred"] == 0


def test_budget_unset_or_garbage_means_read_only(tmp_path: Path, monkeypatch):
    """Missing and invalid settings cannot turn an ordinary read into a producer."""
    net = _net()
    for label, raw in (("unset", None), ("garbage", "many"), ("empty", "")):
        if raw is None:
            monkeypatch.delenv("LAPLACE_EMBED_BUDGET", raising=False)
        else:
            monkeypatch.setenv("LAPLACE_EMBED_BUDGET", raw)
        d = tmp_path / label
        d.mkdir()
        rep = embed_router.ensure_embeddings(d, net, HashBackend())
        assert rep["n_embedded"] == 0 and rep["n_deferred"] == len(net["nodes"]), label
        assert not (d / CACHE_FILE).exists()
        assert not (d / ".metric_M.receipt.json").exists()


def test_budget_zero_is_OFF_the_local_serving_path_never_embeds(tmp_path: Path, monkeypatch, capsys):
    """THE SEMANTIC FLIP (WO-20260715-233320-psu-embed-off; F1 escalated freeze->PSU,
    WALK_2026-07-15): budget=0 (or a negative) now means OFF, not unlimited. A SERVING call
    (bulk=False) embeds NOTHING, defers every stale node, writes no vectors, and announces the
    OFF posture once. This is the pre-2026-07-15 contract's inverse - '0' was unlimited, now it
    is the local box's hard stop against the PSU spike the walk caught."""
    monkeypatch.setattr(embed_router, "_OFF_ANNOUNCED", False)   # deterministic OFF-line capture
    net = _net()
    n = len(net["nodes"])
    for raw in ("0", "-3"):
        monkeypatch.setenv("LAPLACE_EMBED_BUDGET", raw)
        d = tmp_path / f"off{raw}"
        d.mkdir()
        rep = embed_router.ensure_embeddings(d, net, HashBackend())
        assert rep["n_embedded"] == 0, raw
        assert rep["n_deferred"] == n, raw
        assert rep["vectors"] == {}, raw                         # nothing embedded -> nothing to serve yet
        assert not (d / CACHE_FILE).is_file(), raw               # OFF writes NOTHING - not even an empty cache
    assert "embed drip OFF (budget=0)" in capsys.readouterr().out    # the loud OFF line fired


def test_zero_budget_serving_path_performs_zero_embeds(tmp_path: Path, monkeypatch, capsys):
    """The PSU proof at the drip seam: under budget=0 a SERVING call spins the embedder ZERO
    times - backend.embed is never entered - and the OFF line is logged. The power spike the walk
    caught is made IMPOSSIBLE on the local box, not merely throttled. bulk=True still folds (the
    supervised close deposit / remote is never gated by the local OFF budget)."""
    monkeypatch.setattr(embed_router, "_OFF_ANNOUNCED", False)   # deterministic OFF-line capture
    monkeypatch.setenv("LAPLACE_EMBED_BUDGET", "0")
    net = _net()
    b = HashBackend()
    embed_calls: list[list[str]] = []
    real_embed = b.embed
    object.__setattr__(b, "embed", lambda texts: embed_calls.append(list(texts)) or real_embed(texts))

    rep = embed_router.ensure_embeddings(tmp_path, net, b)        # bulk=False: the serving path
    assert embed_calls == [], "the serving path embedded under budget=0 - the PSU spike is back"
    assert rep["n_embedded"] == 0 and rep["n_deferred"] == len(net["nodes"])
    assert "embed drip OFF (budget=0)" in capsys.readouterr().out

    sub = tmp_path / "sub"; sub.mkdir()
    rep_bulk = embed_router.ensure_embeddings(sub, net, b, bulk=True)   # the producer fold ignores OFF
    assert embed_calls and rep_bulk["n_embedded"] == len(net["nodes"])


def test_serving_drip_emits_the_loud_timing_line(tmp_path: Path, monkeypatch, capsys):
    """THE LOUD LINE (WO-20260715-233320-psu-embed-off): a serving-path drip that actually embeds
    (budget>0) prints one unmissable per-batch line carrying the node count, budget, thread cap,
    and wall elapsed - the scanner-side timing line the F1 probe was missing. A bulk producer fold
    stays quiet (its heavy work is intended, reported through n_embedded)."""
    net = _net()
    monkeypatch.setenv("LAPLACE_EMBED_BUDGET", "3")
    monkeypatch.setenv("LAPLACE_EMBED_THREADS", "2")
    rep = embed_router.ensure_embeddings(tmp_path, net, HashBackend())
    out = capsys.readouterr().out
    assert rep["n_embedded"] == 3
    assert "embed_router: DRIP" in out
    assert "embedded=3" in out and "budget=3" in out and "threads=2" in out and "elapsed=" in out

    sub = tmp_path / "bulk"; sub.mkdir()
    embed_router.ensure_embeddings(sub, net, HashBackend(), bulk=True)
    assert "DRIP" not in capsys.readouterr().out         # the producer fold is not a serving drip


def test_budget_off_leaves_the_cache_stale_and_the_read_reports_degraded(tmp_path: Path, monkeypatch):
    """HONEST DEGRADATION (WO-20260715-233320-psu-embed-off): under budget=0 the serving path
    never freshens the cache, so when the graded network moves ahead of it the router-cache read
    stays DEGRADED - the exact server-side flag the approved conceptric `vectors stale - semantic
    rank off` chip reads. The drip-off and the staleness contract are the same posture, told
    truthfully (the read never claims a serve-time self-heal that no longer happens)."""
    import os
    from laplace.web import shared_ui
    from laplace.engine.keeper import GRADED_LOCAL
    net = _net()
    b = HashBackend()
    # a remote/bulk fold once warmed the full cache; then a node mutates -> stale-by-hash
    embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)
    net["nodes"]["b1"]["essence"] = "banana bread, now with chocolate"
    os.utime(tmp_path / CACHE_FILE, (1000, 1000))

    # a budget-0 serving call defers the stale node and does NOT rewrite the cache
    monkeypatch.setenv("LAPLACE_EMBED_BUDGET", "0")
    rep = embed_router.ensure_embeddings(tmp_path, net, b)       # bulk=False
    assert rep["n_embedded"] == 0 and rep["n_deferred"] == 1
    assert (tmp_path / CACHE_FILE).stat().st_mtime == 1000, "budget=0 must not touch the cache"

    # ... so, with the graded network newer than the cache, the read is honestly degraded
    (tmp_path / GRADED_LOCAL).write_text("x", encoding="utf-8")
    os.utime(tmp_path / GRADED_LOCAL, (2000, 2000))
    row = shared_ui.read_router_cache(tmp_path)
    assert row["present"] is True and row["fresh"] is False and row["degraded"] is True
    assert row["reason"] and row["fix"]                          # named, not a silent zero
    assert "never embeds" in row["fix"]                          # the truthful PSU-law contract


def test_route_serves_degraded_but_honest_under_budget(tmp_path: Path, monkeypatch):
    """A budgeted cache still ROUTES: unvectored nodes sit out the descent (vecs.get -> skip),
    the record stays well-formed, and repeated fires drip the cache fuller - the navigator
    serves from the first boot, it just gets sharper as the drip converges."""
    monkeypatch.setenv("LAPLACE_EMBED_BUDGET", "2")
    net = _net()
    rec = embed_router.route(tmp_path, net, "alpha particle physics scattering",
                             backend=HashBackend())
    assert rec is not None and rec["router"] == "hash:3gram-256"
    assert rec["visited"] <= rec["total"]
    # a few more fires and the full-cache ranking is restored
    for _ in range(3):
        rec = embed_router.route(tmp_path, net, "alpha particle physics scattering",
                                 backend=HashBackend())
    assert [f["file"] for f in rec["files"]][0] == "a1"       # the semantic leaf, as ever


def test_cache_is_backend_keyed(tmp_path: Path):
    """A cache built by one geometry is never read as another's - the backend name is in the key."""
    net = _net()
    embed_router.ensure_embeddings(tmp_path, net, HashBackend())
    other = HashBackend()
    other.name = "hash:other"
    rep = embed_router.ensure_embeddings(tmp_path, net, other)
    assert rep["n_embedded"] == len(net["nodes"])    # full re-embed, no cross-model reuse


# ---------------------------------------------------------------------------
# the per-process basis memo (WO-20260821-route-basis-memo, C3a/C3c)
#
# route() used to rebuild the whole basis per fire - re-read the store, re-derive
# node_text over every node, re-hash, dequantize the lot. `basis` memoises it on a
# key covering every input staleness is drawn from. THE ONE FORBIDDEN FAILURE IS
# STALE-CLAIMING-FRESH, so each half of that key is pinned by its own refusal below.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_basis_memo():
    """The memo is per PROCESS, so it must not survive a test - one slot, cleared both ends."""
    embed_router._BASIS_MEMO.clear()
    yield
    embed_router._BASIS_MEMO.clear()


def test_basis_serves_matrix_rows_and_memoises_a_fresh_store(tmp_path: Path):
    import numpy as np
    net, b = _net(), HashBackend()
    embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)      # the producer fold
    first = embed_router.basis(tmp_path, net, b)
    assert first["ids"] == list(first["vectors"])
    assert first["matrix"].shape == (len(net["nodes"]), b.dim)
    assert first["matrix"].dtype == np.dtype("float32")
    for nid in first["ids"]:                                          # rows, not copies
        assert np.shares_memory(first["vectors"][nid], first["matrix"])
    assert first["n_embedded"] == 0 and first["n_deferred"] == 0
    assert embed_router.basis(tmp_path, net, b) is first              # the memo hit: no rebuild


def test_basis_matches_the_vectors_ensure_embeddings_serves(tmp_path: Path):
    """The matrix is the same numbers, decoded in one pass instead of per entry."""
    net, b = _net(), HashBackend()
    rep = embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)
    got = embed_router.basis(tmp_path, net, b)
    for nid, vec in rep["vectors"].items():
        assert list(got["vectors"][nid]) == pytest.approx(vec)


def test_basis_memo_refuses_a_store_another_writer_moved(tmp_path: Path):
    """THE FORBIDDEN FAILURE, first face: the store's BYTES change while nothing in `net` does.
    The content hashes are left untouched, so the staleness scan would call every node fresh -
    only the file's stamp says otherwise. A memo that keyed on the network alone would serve the
    superseded vector and claim it current."""
    import os
    net, b = _net(), HashBackend()
    embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)
    first = embed_router.basis(tmp_path, net, b)
    assert list(first["vectors"]["b1"]) != list(first["vectors"]["a1"])

    cache = tmp_path / CACHE_FILE
    disk = json.loads(cache.read_text(encoding="utf-8"))
    disk["nodes"]["b1"]["q"] = disk["nodes"]["a1"]["q"]      # b1's row replaced, its "h" kept
    disk["nodes"]["b1"]["s"] = disk["nodes"]["a1"]["s"]
    cache.write_text(json.dumps(disk), encoding="utf-8")
    # a real write moves mtime_ns on its own; the bump only keeps filesystem timestamp
    # granularity out of the assertion.
    st = cache.stat()
    os.utime(cache, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

    second = embed_router.basis(tmp_path, net, b)
    assert second is not first
    assert list(second["vectors"]["b1"]) == list(second["vectors"]["a1"])


def test_basis_memo_refuses_a_store_that_grew_with_its_mtime_pinned_back(tmp_path: Path):
    """The other half of the store stamp: SIZE. The mtime is forced back to what it was, so only
    the file's length has moved - and the memo must still refuse."""
    import os
    net, b = _net(), HashBackend()
    embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)
    first = embed_router.basis(tmp_path, net, b)
    cache = tmp_path / CACHE_FILE
    before = cache.stat()

    disk = json.loads(cache.read_text(encoding="utf-8"))
    disk["nodes"]["b1"]["q"] = disk["nodes"]["a1"]["q"]
    disk["nodes"]["b1"]["s"] = disk["nodes"]["a1"]["s"]
    cache.write_text(json.dumps(disk, indent=4), encoding="utf-8")     # same nodes, more bytes
    os.utime(cache, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert cache.stat().st_mtime_ns == before.st_mtime_ns
    assert cache.stat().st_size != before.st_size

    assert embed_router.basis(tmp_path, net, b) is not first


def test_basis_memo_refuses_a_network_mutated_in_place(tmp_path: Path):
    """THE FORBIDDEN FAILURE, second face: the SAME network object, edited in place. Object
    identity cannot see it and no file moved, so the content fingerprint is what refuses - and
    the re-run re-embeds exactly the node whose text moved (the incremental contract, kept)."""
    net, b = _net(), HashBackend()
    embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)
    first = embed_router.basis(tmp_path, net, b)
    net["nodes"]["b1"]["essence"] = "banana bread, now with chocolate"
    second = embed_router.basis(tmp_path, net, b)
    assert second is not first
    assert second["n_embedded"] == 1
    for field, value in (("keywords", ["banana", "bread", "cocoa"]),
                         ("coverage", ["banana", "cocoa"]),
                         ("parent", "A"), ("leaf", False)):
        embed_router._BASIS_MEMO.clear()
        warm = embed_router.basis(tmp_path, net, b)
        assert embed_router.basis(tmp_path, net, b) is warm
        net["nodes"]["b1"][field] = value
        assert embed_router.basis(tmp_path, net, b) is not warm, f"{field} must invalidate"


def test_basis_memo_refuses_an_ancestors_kind_flip(tmp_path: Path):
    """THE FORBIDDEN FAILURE, upward face. A node's text is not a function of its own fields:
    `node_text` walks three rungs and `_ancestor_label` branches on the ANCESTOR's `kind` - a
    'concept' rung is dropped, any other kind contributes its id tail. So flipping A's kind
    rewrites both of A's leaves while nothing on those leaves moved. The key covers it because
    every node is stamped, A included."""
    net, b = _net(), HashBackend()
    net["nodes"]["A"]["kind"] = "concept"
    embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)
    warm = embed_router.basis(tmp_path, net, b)
    assert embed_router.basis(tmp_path, net, b) is warm
    before = embed_router.node_text(tmp_path, net, "a1")
    net["nodes"]["A"]["kind"] = "file"
    assert embed_router.node_text(tmp_path, net, "a1") != before      # the rung arrived
    after = embed_router.basis(tmp_path, net, b)
    assert after is not warm, "an ancestor's kind must invalidate"
    assert after["n_embedded"] == 2, "both of A's leaves re-embed, and nothing else does"


def test_basis_memo_refuses_a_second_network_object(tmp_path: Path):
    """Two networks never share a slot, whatever their fingerprints say: the memo requires the
    caller's `net` to be the same OBJECT, so a fresh load is always a fresh basis."""
    b = HashBackend()
    net = _net()
    embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)
    first = embed_router.basis(tmp_path, net, b)
    assert embed_router.basis(tmp_path, _net(), b) is not first        # same content, new object


def test_basis_memo_refuses_a_different_backend(tmp_path: Path):
    """The backend name rides every content hash, so it rides the memo key."""
    net, b = _net(), HashBackend()
    embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)
    first = embed_router.basis(tmp_path, net, b)
    other = HashBackend()
    other.name = "hash:other"
    assert embed_router.basis(tmp_path, net, other) is not first


def test_a_drip_is_never_memoised(tmp_path: Path, monkeypatch):
    """Under a positive budget the serving path embeds PART of the stale set per call and defers
    the rest; memoising that would freeze the cache mid-walk. The memo stands aside until there
    is nothing left to do."""
    monkeypatch.setenv("LAPLACE_EMBED_BUDGET", "2")
    net, b = _net(), HashBackend()
    first = embed_router.basis(tmp_path, net, b)
    assert first["n_embedded"] == 2 and first["n_deferred"] == len(net["nodes"]) - 2
    second = embed_router.basis(tmp_path, net, b)
    assert second is not first and second["n_embedded"] == 2          # the drip walked on
    third = embed_router.basis(tmp_path, net, b)
    assert third["n_embedded"] == 2 and third["n_deferred"] == 0       # the last of the drip
    # nothing deferred any more, so THAT call's basis is the one memoised - and its report keeps
    # describing the build that produced it (2 embedded), never the call that re-served it.
    assert embed_router.basis(tmp_path, net, b) is third


def test_the_off_posture_memoises_because_a_rerun_is_bit_identical(tmp_path: Path, monkeypatch):
    """budget=0 is OFF: the serving path embeds NOTHING, ever. The stale set is deferred on every
    call, so re-deriving it changes nothing - and the deferred count still rides the report."""
    monkeypatch.setenv("LAPLACE_EMBED_BUDGET", "0")
    net, b = _net(), HashBackend()
    first = embed_router.basis(tmp_path, net, b)
    assert first["n_embedded"] == 0 and first["n_deferred"] == len(net["nodes"])
    assert embed_router.basis(tmp_path, net, b) is first


def test_bulk_neither_reads_nor_writes_the_memo(tmp_path: Path):
    """The producer path is the one that WRITES the store; it must always re-derive, and it must
    not evict the serving slot it never consulted."""
    net, b = _net(), HashBackend()
    warm = embed_router.basis(tmp_path, net, b)
    assert embed_router.basis(tmp_path, net, b) is warm
    assert embed_router.basis(tmp_path, net, b, bulk=True) is not warm
    assert embed_router.basis(tmp_path, net, b) is warm


def test_route_reuses_the_basis_across_fires(tmp_path: Path, monkeypatch):
    """The lane's point: fourteen thread probes in one process build the basis ONCE."""
    net, b = _net(), HashBackend()
    embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)
    calls = {"n": 0}
    real = embed_router.ensure_embeddings
    monkeypatch.setattr(embed_router, "ensure_embeddings",
                        lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or real(*a, **k))
    for q in ("alpha particle", "banana bread", "alpha decay"):
        assert embed_router.route(tmp_path, net, q, backend=b) is not None
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# the route - descent by cosine, paths root-first, salience over the pull
# ---------------------------------------------------------------------------

def test_route_finds_the_semantic_leaf(tmp_path: Path):
    net = _net()
    rec = embed_router.route(tmp_path, net, "alpha particle physics scattering",
                             backend=HashBackend())
    assert rec["router"] == "hash:3gram-256"
    files = [f["file"] for f in rec["files"]]
    assert files[0] == "a1"
    top = rec["files"][0]
    assert top["path"] == ["root", "A", "a1"]        # root-first, the full descent
    assert 0.0 <= top["score"] <= 1.0
    assert rec["visited"] <= rec["total"]
    # every grade fired: direct hits exist at g0 and g1
    assert "0" in rec["per_grade_direct"] and "1" in rec["per_grade_direct"]


def test_route_none_without_backend(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(embed_router, "get_backend", lambda: None)
    assert embed_router.route(tmp_path, _net(), "anything") is None


def test_per_grade_merge_keeps_each_shards_best(tmp_path: Path):
    """Mind sharding's merge: a thin shard's local best survives a fat shard's flood - top-w
    PER SHARD per grade, so no branch's floor is drowned by another branch's mass."""
    fat_leaves = {f"f{i}": {"id": f"f{i}", "grade": 0, "parent": "FAT", "leaf": True,
                            "members": [], "coverage": [], "keywords": ["alpha"],
                            "essence": f"alpha particle measurement run {i}"}
                  for i in range(15)}
    nodes = {
        "root": {"id": "root", "grade": 2, "parent": None, "leaf": False,
                 "members": ["FAT", "THIN"], "coverage": [], "keywords": [],
                 "essence": "everything"},
        "FAT": {"id": "FAT", "grade": 1, "parent": "root", "leaf": False,
                "members": sorted(fat_leaves), "coverage": ["alpha"], "keywords": ["alpha"],
                "essence": "alpha particle measurements"},
        "THIN": {"id": "THIN", "grade": 1, "parent": "root", "leaf": False, "members": ["t1"],
                 "coverage": ["alpine"], "keywords": ["alpine"],
                 "essence": "alpine hiking notes"},
        "t1": {"id": "t1", "grade": 0, "parent": "THIN", "leaf": True, "members": [],
               "coverage": [], "keywords": ["alpine"], "essence": "alpine trail map"},
        **fat_leaves,
    }
    net = {"nodes": nodes, "reach": {n: set() for n in nodes},
           "lenses": {n: ["engine"] for n in nodes}, "root": "root"}
    rec = embed_router.route(tmp_path, net, "alpha particle measurement",
                             backend=HashBackend())
    g0 = rec["per_grade_direct"]["0"]
    ids = [e["id"] for e in g0]
    assert "t1" in ids                       # the thin shard's best is in the merge
    assert sum(1 for i in ids if i.startswith("f")) <= embed_router.PER_BRANCH_WIDTH


# ---------------------------------------------------------------------------
# fire_by_grade integration - the embedding router fires; the fallback is marked
# ---------------------------------------------------------------------------

def test_fire_by_grade_uses_embedding_router(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(embed_router, "get_backend", lambda: HashBackend())
    net = _net()
    out = conceptric.fire_by_grade(tmp_path, net, "alpha particle physics scattering")
    assert out["router"] == "hash:3gram-256+lex"   # geometry + the identity channel, marked
    assert out["hits"][0]["recovered"] == "a1"
    # the direct per-grade firing is salience-merged into the buckets
    assert any(e["id"] in ("A", "B") for e in out["per_grade"].get("1", []))


def test_identity_channel_recovers_what_geometry_misses(tmp_path: Path, monkeypatch):
    """Names are symbolic: 'Guy Skinner' (two common words) embedded nowhere near his entity
    while token overlap found him instantly - the bench's first live catch (2026-06-11). The
    lexical ring now ALWAYS fires beside the geometry and the recall is salience-merged, each
    hit carrying its channel."""
    monkeypatch.setattr(embed_router, "get_backend", lambda: HashBackend())
    # geometry returns confident junk that does NOT contain the keyword-matching leaf
    junk = {"query": "g", "router": "hash:3gram-256", "visited": 2, "total": 5,
            "files": [{"file": "f1", "score": 0.9, "cos": 0.5,
                       "path": ["root", "f1"], "why": {"lexical": []}}],
            "per_grade_direct": {}, "proposals": [],
            "geometry": {"beam": 8, "per_branch_width": 12, "path_decay": 0.9, "limit": 10}}
    monkeypatch.setattr(embed_router, "route", lambda *a, **k: dict(junk, files=[dict(junk["files"][0])]))
    net = _net()
    out = conceptric.fire_by_grade(tmp_path, net, "alpha particle")
    assert out["router"].endswith("+lex")
    ids = [h["recovered"] for h in out["hits"]]
    assert "a1" in ids, "the keyword-matching leaf must ride in on the identity channel"
    lex_hit = next(h for h in out["hits"] if h["recovered"] == "a1")
    assert lex_hit["why"]["channel"] == "lexical"
    assert "alpha" in lex_hit["why"]["lexical"]
    geo_hit = next(h for h in out["hits"] if h["recovered"] == "f1")
    assert geo_hit["why"]["channel"] == "geometric"


def test_fire_by_grade_falls_back_marked(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(embed_router, "get_backend", lambda: None)
    net = _net()
    out = conceptric.fire_by_grade(tmp_path, net, "alpha")
    assert out["router"] == "lexical-fallback"
    assert any(h["recovered"] == "a1" for h in out["hits"])      # the lexical ring still recalls


def test_compare_variants_are_real_fires(tmp_path: Path, monkeypatch):
    """The comparison fire's variants are the ENGINE's own switches, never view math:
    use_metric=False fires raw cosine; force_router='lexical' fires the lexical ring, marked."""
    monkeypatch.setattr(embed_router, "get_backend", lambda: HashBackend())
    net = _net()
    raw = conceptric.fire_by_grade(tmp_path, net, "alpha particle physics", use_metric=False)
    assert raw["router"] == "hash:3gram-256+lex"       # no +M suffix - the metric did not ride
    lex = conceptric.fire_by_grade(tmp_path, net, "alpha", force_router="lexical")
    assert lex["router"] == "lexical"                  # forced, not a fallback
    assert any(h["recovered"] == "a1" for h in lex["hits"])


def test_wire_audit_dedupe_verdicts_and_learning(tmp_path: Path):
    """The N29 audit mechanics: the ledger dedupes to pairs; a 'wire' verdict TEACHES THE
    SYMBOLS (query tokens join the node's learned keywords, merged at network load, so the
    graph explains the find forever after); grit/noise bank as record only; judged pairs
    leave the proposals ledger."""
    ledger = tmp_path / embed_router.PROPOSALS_FILE
    rows = [{"query": "the weld covenant", "id": "EIGEN_DIARY.md::33", "cos": 0.8, "via": "x"},
            {"query": "the weld covenant", "id": "EIGEN_DIARY.md::33", "cos": 0.9, "via": "x"},
            {"query": "guy skinner", "id": "src/laplace/engine/assess.py", "cos": 0.5, "via": "y"},
            {"query": "guy skinner", "id": "tests/test_laplace.py", "cos": 0.5, "via": "y"}]
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    pairs = embed_router.proposal_pairs(tmp_path)
    assert len(pairs) == 3, "duplicates collapse to unique (query, id) pairs"
    assert next(p for p in pairs if p["id"] == "EIGEN_DIARY.md::33")["cos"] == 0.9

    out = embed_router.bank_verdicts(tmp_path, [
        {"query": "the weld covenant", "id": "EIGEN_DIARY.md::33", "verdict": "wire", "why": "real"},
        {"query": "guy skinner", "id": "src/laplace/engine/assess.py", "verdict": "noise", "why": "band"},
    ])
    assert out == {"wire": 1, "noise": 1, "grit": 0, "n_learned_nodes": 1, "n_remaining": 1}
    learned = embed_router.load_learned_keywords(tmp_path)
    assert "weld" in learned["EIGEN_DIARY.md::33"] and "covenant" in learned["EIGEN_DIARY.md::33"]
    assert len(embed_router.proposal_pairs(tmp_path)) == 1     # the unjudged frontier remains
    assert (tmp_path / embed_router.VERDICTS_FILE).is_file()

    # the loader merge: the learned tokens join the node at load (symbol AND geometry)
    from laplace.engine import conceptric
    (tmp_path / "EIGEN_DIARY.md").write_text("# d\n\nbody\n", encoding="utf-8")
    net = conceptric.load_network(tmp_path)
    if "EIGEN_DIARY.md::33" in net["nodes"]:
        assert "weld" in net["nodes"]["EIGEN_DIARY.md::33"]["keywords"]
    learned2 = {"EIGEN_DIARY.md": ["weld", "covenant"]}
    (tmp_path / embed_router.LEARNED_KEYWORDS_FILE).write_text(json.dumps(learned2), encoding="utf-8")
    net = conceptric.load_network(tmp_path)
    assert "weld" in net["nodes"]["EIGEN_DIARY.md"]["keywords"]
    assert "covenant" in net["nodes"]["EIGEN_DIARY.md"]["coverage"]


def test_mechanical_verdicts_embeds_only_the_frontier_ids(tmp_path: Path, monkeypatch):
    """Gate B (his ruling 2026-07-13: the close pays only for what moved). mechanical_verdicts must
    embed/lookup ONLY the node ids the frontier references - never the network-wide ensure_embeddings
    (whose unconditional re-embed was ~all of the wire phase). Here: a 2-pair frontier over a 6-node
    net; ensure_embeddings must NOT be called, and backend.embed must fire once with exactly the two
    frontier node texts (batched)."""
    net = _net()
    b = HashBackend()
    monkeypatch.setattr(embed_router, "get_backend", lambda: b)

    ensure_calls = {"n": 0}
    monkeypatch.setattr(embed_router, "ensure_embeddings",
                        lambda *a, **k: ensure_calls.__setitem__("n", ensure_calls["n"] + 1) or {"vectors": {}})

    embed_batches: list[list[str]] = []
    real_embed = b.embed
    monkeypatch.setattr(b, "embed", lambda texts: embed_batches.append(list(texts)) or real_embed(texts))

    rows = [{"query": "alpha particle physics scattering", "id": "a1", "cos": 0.6, "via": "A"},
            {"query": "banana bread recipe with walnuts", "id": "b1", "cos": 0.6, "via": "B"}]
    (tmp_path / embed_router.PROPOSALS_FILE).write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    verdicts = embed_router.mechanical_verdicts(tmp_path, net)

    assert ensure_calls["n"] == 0, "the network-wide ensure_embeddings must not be called on the wire step"
    assert len(embed_batches) == 1, "the frontier-id misses are embedded in ONE batch"
    assert set(embed_batches[0]) == {embed_router.node_text(tmp_path, net, "a1"),
                                     embed_router.node_text(tmp_path, net, "b1")}

    # verdicts identical to computing the gate from the SAME per-id vectors (the old path's result for
    # these ids) - only the SET of vectors materialized narrowed, never the decision.
    import numpy as np
    expected = []
    for r in rows:
        v = np.asarray(real_embed([embed_router.node_text(tmp_path, net, r["id"])])[0], dtype=np.float64)
        v = v / (np.linalg.norm(v) or 1.0)
        c = float(np.asarray(b.query(r["query"]), dtype=np.float64) @ v)
        g = embed_router.mechanical_gate(c)
        if g:
            expected.append((r["query"], r["id"], g, round(c, 4)))
    got = [(x["query"], x["id"], x["verdict"], x["cos"]) for x in verdicts]
    assert got == expected


def test_mechanical_verdicts_empty_frontier_is_a_noop(tmp_path: Path, monkeypatch):
    """No frontier -> no embed, no ensure_embeddings, empty verdicts (the deposit's Gate-A skip relies
    on this being cheap even if it is reached)."""
    net = _net()
    b = HashBackend()
    monkeypatch.setattr(embed_router, "get_backend", lambda: b)
    ensure_calls = {"n": 0}
    monkeypatch.setattr(embed_router, "ensure_embeddings",
                        lambda *a, **k: ensure_calls.__setitem__("n", ensure_calls["n"] + 1) or {"vectors": {}})
    assert embed_router.mechanical_verdicts(tmp_path, net) == []
    assert ensure_calls["n"] == 0


def test_jury_briefs_reuse_only_source_receipted_local_frames(tmp_path: Path):
    """An unchanged 8k-pair jury frontier must not reconstruct 8k local frames each close.

    Reuse is licensed by the pair + dependency hashes. An unrelated edit is irrelevant;
    moving the node row that produced one brief rebuilds that brief only.
    """
    net = _net()
    pairs = [
        {"query": "alpha", "id": "a1", "cos": 0.6, "via": "A"},
        {"query": "beta", "id": "b1", "cos": 0.6, "via": "B"},
    ]
    first, rep1 = embed_router.audit_briefs_incremental(tmp_path, net, pairs=pairs)
    assert rep1 == {"total": 2, "reused": 0, "rebuilt": 2, "dropped": 0}
    assert all(b.get("_source_ids") and b.get("_source_fingerprint") for b in first)

    same, rep2 = embed_router.audit_briefs_incremental(tmp_path, net, first, pairs=pairs)
    assert rep2 == {"total": 2, "reused": 2, "rebuilt": 0, "dropped": 0}
    assert same == first

    net["nodes"]["A"]["essence"] = "alpha ancestor moved"
    partial, rep3 = embed_router.audit_briefs_incremental(tmp_path, net, first, pairs=pairs)
    assert rep3["reused"] == 1 and rep3["rebuilt"] == 1
    assert partial[0]["_source_fingerprint"] != first[0]["_source_fingerprint"]
    assert partial[1] == first[1]

    net["nodes"]["a1"]["essence"] = "alpha moved"
    moved, rep4 = embed_router.audit_briefs_incremental(tmp_path, net, partial, pairs=pairs)
    assert rep4["reused"] == 1 and rep4["rebuilt"] == 1
    assert moved[0]["_source_fingerprint"] != first[0]["_source_fingerprint"]

    _, rep5 = embed_router.audit_briefs_incremental(tmp_path, net, moved, pairs=pairs[:1])
    assert rep5["total"] == 1 and rep5["dropped"] == 1


def test_frontier_vectors_serves_cache_hits_and_batches_misses(tmp_path: Path):
    """_frontier_vectors: a content-hash cache HIT is served from disk (no embed); the misses are
    embedded in one batch. Read-only on the cache - it never rewrites .self_embeddings.json (a partial
    write keyed only by the frontier would clobber the network), so the vanished-node prune stays with
    route()'s ensure_embeddings."""
    net = _net()
    b = HashBackend()
    # warm the cache for the whole net (this is route()'s lazy call, the legitimate writer/pruner)
    embed_router.ensure_embeddings(tmp_path, net, b)
    before = (tmp_path / embed_router.CACHE_FILE).read_bytes()

    embed_batches: list[list[str]] = []
    real_embed = b.embed
    b_embed_spy = lambda texts: embed_batches.append(list(texts)) or real_embed(texts)
    object.__setattr__(b, "embed", b_embed_spy)

    out = embed_router._frontier_vectors(tmp_path, net, b, {"a1", "b1"})
    assert set(out) == {"a1", "b1"}
    assert embed_batches == [], "both ids were cache hits - no re-embed"
    # a miss (an id whose text isn't cached) batches with any other miss, cache untouched on disk
    out2 = embed_router._frontier_vectors(tmp_path, net, b, {"a1", "not_a_node"})
    assert set(out2) == {"a1", "not_a_node"}
    assert embed_batches == [["not_a_node"]], "only the miss is embedded"
    assert (tmp_path / embed_router.CACHE_FILE).read_bytes() == before, "cache is not rewritten"


def test_ledger_records_carry_ts_and_old_records_still_parse(tmp_path: Path):
    """Per-period trend analysis needs a timestamp on every banked record (the audit-effect
    meter's named gap). Both write sites - route()'s proposal append and bank_verdicts - now
    stamp a UTC ISO-8601 (seconds) ``ts``; readers built before this field existed must keep
    parsing ts-less lines untouched (dict.get access, never a strict schema)."""
    net = _net()
    rec = embed_router.route(tmp_path, net, "scattering physics", backend=HashBackend())
    assert rec["proposals"], "expected a geometric-only find to bank a proposal"
    ledger_lines = [json.loads(ln) for ln in
                    (tmp_path / embed_router.PROPOSALS_FILE).read_text(encoding="utf-8").splitlines()]
    for p in ledger_lines:
        assert "ts" in p and p["ts"], "every freshly-banked proposal carries a non-empty ts"
        datetime.fromisoformat(p["ts"])           # parses as a real UTC ISO-8601 timestamp

    out = embed_router.bank_verdicts(tmp_path, [
        {"query": "scattering physics", "id": ledger_lines[0]["id"], "verdict": "grit", "why": "x"},
    ])
    assert out["grit"] == 1
    verdict_lines = [json.loads(ln) for ln in
                     (tmp_path / embed_router.VERDICTS_FILE).read_text(encoding="utf-8").splitlines()]
    assert verdict_lines and all("ts" in v and v["ts"] for v in verdict_lines)
    datetime.fromisoformat(verdict_lines[-1]["ts"])

    # an old, ts-less line (pre-fix ledger shape) must still parse through the readers unharmed
    old_proposals = tmp_path / embed_router.PROPOSALS_FILE
    old_proposals.write_text(json.dumps({"query": "legacy", "id": "a1", "cos": 0.5, "via": None}) + "\n",
                             encoding="utf-8")
    pairs = embed_router.proposal_pairs(tmp_path)
    assert pairs == [{"query": "legacy", "id": "a1", "cos": 0.5, "heat": None, "via": None}]

    old_verdict_line = json.dumps({"query": "legacy", "id": "a1", "verdict": "noise", "why": "b"})
    parsed = json.loads(old_verdict_line)
    assert parsed.get("ts") is None                    # pre-fix records have no ts - readers must .get(), never require it
    assert parsed["verdict"] == "noise"                # the record is otherwise fully usable


def test_proposal_pairs_keeps_earliest_ts_independent_of_cos_winner(tmp_path: Path):
    """proposal_pairs dedupes to the max-cos line per pair, but ts tracks the EARLIEST line
    seen for that pair regardless of which line's cos wins - the pair's first-proposed time,
    not the winning re-fire's time."""
    rows = [
        {"query": "q", "id": "n1", "cos": 0.5, "via": "a", "ts": "2026-07-01T10:00:00+00:00"},
        {"query": "q", "id": "n1", "cos": 0.9, "via": "a", "ts": "2026-07-03T10:00:00+00:00"},
        {"query": "q", "id": "n1", "cos": 0.3, "via": "a", "ts": "2026-06-30T09:00:00+00:00"},
    ]
    (tmp_path / embed_router.PROPOSALS_FILE).write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    pairs = embed_router.proposal_pairs(tmp_path)
    assert len(pairs) == 1
    p = pairs[0]
    assert p["cos"] == 0.9                                  # the max-cos line still wins the dedupe
    assert p["ts"] == "2026-06-30T09:00:00+00:00"            # but ts is the EARLIEST of the three


def test_bank_verdicts_drain_preserves_ts_on_remaining_frontier(tmp_path: Path):
    """The frontier rewrite in bank_verdicts (~:628) sources straight from proposal_pairs; a
    row left in the frontier after a drain must keep its ts, not have it silently stripped."""
    rows = [
        {"query": "qa", "id": "idA", "cos": 0.9, "via": None, "ts": "2026-07-01T00:00:00+00:00"},
        {"query": "qb", "id": "idB", "cos": 0.8, "via": None, "ts": "2026-07-02T00:00:00+00:00"},
    ]
    (tmp_path / embed_router.PROPOSALS_FILE).write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    embed_router.bank_verdicts(tmp_path, [
        {"query": "qa", "id": "idA", "verdict": "noise", "why": "x"},
    ])
    remaining = embed_router.proposal_pairs(tmp_path)
    assert len(remaining) == 1
    assert remaining[0]["id"] == "idB"
    assert remaining[0]["ts"] == "2026-07-02T00:00:00+00:00"    # ts survived the drain's rewrite
    # the on-disk ledger itself carries it too, not just the in-memory dedupe view
    lines = [json.loads(ln) for ln in
             (tmp_path / embed_router.PROPOSALS_FILE).read_text(encoding="utf-8").splitlines()]
    assert lines == [{"query": "qb", "id": "idB", "cos": 0.8, "via": None,
                      "heat": None, "ts": "2026-07-02T00:00:00+00:00"}]


def test_fire_geometry_knobs_ride_through_and_echo(tmp_path: Path, monkeypatch):
    """The reconstruction geometry is LIVE-TUNABLE on the engine's own call (the cockpit's
    controls): beam/per_branch_width/path_decay turn the router, ancestor_decay the salience
    fade, and the fire ECHOES the values it actually ran with - the view shows the mechanism's
    own numbers, never its assumption of the defaults (view-equals-mechanism)."""
    monkeypatch.setattr(embed_router, "get_backend", lambda: HashBackend())
    net = _net()
    out = conceptric.fire_by_grade(tmp_path, net, "alpha particle physics scattering",
                                   beam=3, per_branch_width=5, path_decay=0.7,
                                   ancestor_decay=0.5, limit=4)
    g = out["geometry"]
    assert g["beam"] == 3 and g["per_branch_width"] == 5
    assert g["path_decay"] == 0.7 and g["ancestor_decay"] == 0.5 and g["limit"] == 4
    # defaults are echoed too, so the cockpit never has to guess what fired
    base = conceptric.fire_by_grade(tmp_path, net, "alpha particle physics scattering")
    bg = base["geometry"]
    assert bg["beam"] == embed_router.BEAM
    assert bg["per_branch_width"] == embed_router.PER_BRANCH_WIDTH
    assert bg["path_decay"] == embed_router.PATH_DECAY
    assert bg["ancestor_decay"] == conceptric.ANCESTOR_DECAY
    # path_decay=0: a handle speaks only for itself - inherited heat dies, own cosine rules.
    cold = conceptric.fire_by_grade(tmp_path, net, "alpha particle physics scattering",
                                    path_decay=0.0)
    assert cold["geometry"]["path_decay"] == 0.0
    assert any(h["recovered"] == "a1" for h in cold["hits"])     # the direct hit still recovers


# ---------------------------------------------------------------------------
# the why-handle - geometry may find, the graph must explain
# ---------------------------------------------------------------------------

def test_hits_carry_their_why(tmp_path: Path):
    net = _net()
    rec = embed_router.route(tmp_path, net, "alpha particle", backend=HashBackend())
    top = rec["files"][0]
    assert top["file"] == "a1"
    why = top["why"]
    assert why["own_cos"] == top["cos"]
    assert "alpha" in why["lexical"]                 # the graph explains this hit
    assert why["geometric_only"] is False
    assert rec["proposals"] == []


def test_geometric_only_find_is_banked(tmp_path: Path):
    """A hit the symbolic layer cannot explain is flagged and banked as a wire-proposal -
    surfaced for the dream's audit, never silently trusted."""
    net = _net()
    embed_router.ensure_embeddings(tmp_path, net, HashBackend(), bulk=True)
    rec = embed_router.route(tmp_path, net, "scattering physics", backend=HashBackend())
    flagged = [f for f in rec["files"] if f["why"]["geometric_only"]]
    assert flagged, "expected at least one geometric-only find for an off-vocabulary query"
    assert rec["proposals"] and rec["proposals"][0]["query"] == "scattering physics"
    ledger = tmp_path / embed_router.PROPOSALS_FILE
    assert not ledger.exists(), "ordinary retrieval returns proposals without recording"
    rec = embed_router.route(tmp_path, net, "scattering physics", backend=HashBackend(), record_proposals=True)
    assert ledger.is_file()
    lines = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert {p["id"] for p in lines} == {p["id"] for p in rec["proposals"]}


# ---------------------------------------------------------------------------
# the trained metric - applied when present, marked in the router name
# ---------------------------------------------------------------------------

def test_route_applies_metric_when_present(tmp_path: Path):
    np = pytest.importorskip("numpy")
    b = HashBackend()
    embed_router.ensure_embeddings(tmp_path, _net(), b, bulk=True)
    np.savez(tmp_path / embed_router.METRIC_FILE, M=np.eye(b.dim, dtype="float32"))
    (tmp_path / ".metric_pairs.json").write_text("{}")
    (tmp_path / ".metric_M.receipt.json").write_text(json.dumps({"pending": {}, "banked": {
        "shipped": True, "metric_hash": embed_router._file_digest(tmp_path / embed_router.METRIC_FILE),
        "pairs_handle": embed_router._file_digest(tmp_path / ".metric_pairs.json"),
        "store_after": {CACHE_FILE: embed_router._file_digest(tmp_path / CACHE_FILE)}}}))
    rec = embed_router.route(tmp_path, _net(), "alpha particle", backend=b)
    assert rec["router"].endswith("+M")
    # identity metric must not change the ranking
    bare = tmp_path / "no_metric"
    bare.mkdir()
    embed_router.ensure_embeddings(bare, _net(), b, bulk=True)
    plain = embed_router.route(bare, _net(), "alpha particle", backend=b)
    assert [f["file"] for f in rec["files"]] == [f["file"] for f in plain["files"]]


# ---------------------------------------------------------------------------
# THE UNSEAL (his definitive verdict, 2026-07-12; PV-20260712-f11-the-unseal):
# the soul-carrying caches now TRAVEL in the private repo — "local or remote
# it's just us". This test used to enforce the 2026-06-08 seal; it now pins the
# superseding law so a re-seal is a deliberate act, not gitignore drift.
# ---------------------------------------------------------------------------

def test_vector_caches_travel_per_the_unseal():
    gi = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")
    active = [ln.strip() for ln in gi.splitlines()
              if ln.strip() and not ln.strip().startswith("#")]
    # CACHE_FILE joins the travelling set as of W6.2 (2026-07-14 banked-what-travels): the
    # 96M raw-float JSON that pinned it against the 100MB wall is replaced by ~8M per-vector
    # int8, so the last warm-arrival hole is closed and the cache is TRACKED like its siblings.
    for name in (embed_router.METRIC_FILE, embed_router.PROPOSALS_FILE, CACHE_FILE):
        assert not any(name in rule for rule in active), (
            f"{name} is ignored again — contradicts PV-20260712-f11-the-unseal / W6.2 "
            "banked-what-travels; re-sealing must go through a contest record, not gitignore drift")


def test_act_sufficient_pool_recovers_handles_not_substrate(tmp_path: Path):
    # the verbatim-floor lesson (hello gate 1/5): a child whose own cosine did not BEAT its
    # parent's heat yields to the handle - act-sufficient recovery; a generic pull returns
    # handles, a specific pull punches through (the leaf tests above pin the punch-through).
    net = _net()
    rec = embed_router.route(tmp_path, net, "the alpha cluster - particle physics notes",
                             backend=HashBackend())
    files = [f["file"] for f in rec["files"]]
    assert "A" in files                       # the cluster handle answers the cluster-shaped pull
    assert "a2" not in files                  # its child did not beat it -> absorbed, not listed


def test_direct_members_keep_their_shard_bucket(tmp_path: Path):
    # the standing-five lesson: an apex member's DIRECT members are attributed to it by
    # MEMBERSHIP (apex order), never to the hottest path - a richer sibling shard cannot
    # claim-and-drown them out of the per-grade survey.
    nodes = {
        "root": {"id": "root", "grade": 3, "parent": None, "leaf": False,
                 "members": ["S", "R"], "coverage": [], "keywords": []},
        "S": {"id": "S", "grade": 2, "parent": "root", "leaf": False, "members": ["s1"],
              "coverage": [], "keywords": [], "essence": "the standing shard - fixed point"},
        "R": {"id": "R", "grade": 2, "parent": "root", "leaf": False,
              "members": ["s1"] + [f"r{i}" for i in range(14)],   # R also lists s1 (overlay-style)
              "coverage": [], "keywords": [],
              "essence": "standing aim goals flood session records"},
        "s1": {"id": "s1", "grade": 0, "parent": "S", "leaf": True, "members": [],
               "coverage": [], "keywords": [], "essence": "protocol covenant wake ritual"},
    }
    for i in range(14):
        nodes[f"r{i}"] = {"id": f"r{i}", "grade": 0, "parent": "R", "leaf": True, "members": [],
                          "coverage": [], "keywords": [],
                          "essence": f"standing aim goals flood session record {i}"}
    net = {"nodes": nodes, "reach": {n: set() for n in nodes},
           "lenses": {n: ["engine"] for n in nodes}, "root": "root"}
    rec = embed_router.route(tmp_path, net, "standing aim goals flood session record",
                             backend=HashBackend())
    g0 = {e["id"] for e in rec["per_grade_direct"].get("0", [])}
    assert "s1" in g0                         # S's direct member survives in S's own bucket


# ---------------------------------------------------------------------------
# failure-shaped query expansion (dream audit 2026-07-11, "the voice that
# didn't surface") - a distress-phrased query loses the provisioning fact to
# sibling evidence-of-past-failure on shared failure vocabulary; the neutral
# phrasing of the SAME need never had the problem.
# ---------------------------------------------------------------------------

def test_failure_shape_detector_fires_on_distress_vocabulary_only():
    fires = ["voice store missing", "voice wash unavailable", "the wash refused",
             "ingest failed", "no store at that path", "config file not found",
             "the pipeline is broken", "a rendering error"]
    for q in fires:
        assert embed_router._FAILURE_SHAPE_RE.search(q), q
    quiet = ["where do voice exemplars live", "how is the voice store provisioned",
             "alpha particle physics", "the standing five"]
    for q in quiet:
        assert not embed_router._FAILURE_SHAPE_RE.search(q), q


def test_failure_shape_rephrase_strips_distress_keeps_subject():
    r = embed_router._failure_shaped_rephrase("voice store missing")
    assert r == "where does voice store live / how is voice store provisioned"
    # neutral phrasing - detector doesn't fire, nothing to rephrase
    assert embed_router._failure_shaped_rephrase("where do voice exemplars live") is None
    # all-distress, no surviving subject - conservative no-op, not a garbage rewrite
    assert embed_router._failure_shaped_rephrase("missing") is None


def _voice_incident_net(n_wash: int = 6) -> dict:
    """The dream audit's own case, reconstructed as a minimal fixture: SUBSTRATE is the
    rebuildable-store fact (`voice store lives at voice_corpus exemplars ... provisioned by
    running ingest`); the WASH siblings are evidence blobs of past failed washes - they share
    the failure vocabulary with a distress-phrased query and outscore the substrate on it,
    exactly the audit's measured defect (rank 16-17-or-nowhere on 'voice store missing' /
    'voice wash unavailable', rank 1 on the neutral 'where do voice exemplars live')."""
    nodes = {
        "root": {"id": "root", "grade": 1, "parent": None, "leaf": False,
                 "members": ["SUBSTRATE"] + [f"WASH{i}" for i in range(1, n_wash + 1)],
                 "coverage": [], "keywords": [], "essence": "voice pipeline root"},
        "SUBSTRATE": {"id": "SUBSTRATE", "grade": 0, "parent": "root", "leaf": True,
                      "members": [], "coverage": [], "keywords": [],
                      "essence": "where does the voice store live: voice_corpus exemplars, "
                                 "the committed raw; how is the voice store provisioned: run "
                                 "the deterministic ingest rebuild command"},
    }
    for i in range(1, n_wash + 1):
        nodes[f"WASH{i}"] = {
            "id": f"WASH{i}", "grade": 0, "parent": "root", "leaf": True, "members": [],
            "coverage": [], "keywords": [],
            "essence": f"voice wash refused: store missing, voice store unavailable, "
                       f"attempt {i} failed broken error"}
    return {"nodes": nodes, "reach": {n: set() for n in nodes},
            "lenses": {n: ["engine"] for n in nodes}, "root": "root"}


def test_distress_phrasing_loses_the_fact_without_expansion(tmp_path: Path):
    """Pins the measured defect itself: on the raw distress phrasing, the provisioning fact
    is NOT in the top-3 - the wash-evidence siblings, sharing the failure vocabulary, outrank
    it - matching the audit's 16th-or-nowhere finding qualitatively."""
    net = _voice_incident_net()
    rec = embed_router.route(tmp_path, net, "voice store missing", backend=HashBackend(),
                             expand_failure_shaped=False)
    files = [f["file"] for f in rec["files"]]
    assert files.index("SUBSTRATE") >= 3           # outside the top-3 - the defect, reproduced


def test_expansion_recovers_top3_rank_on_distress_phrasing(tmp_path: Path):
    """The fix: with expansion ON (the default), the same distress query's candidate pool is
    merged with its provisioning-shaped rephrase's pool by max-score-per-candidate, and the
    fact climbs into the top-3 - here, to rank 1, since its OWN text answers the rephrase
    directly while the wash-evidence siblings do not."""
    net = _voice_incident_net()
    before = embed_router.route(tmp_path, net, "voice store missing", backend=HashBackend(),
                                expand_failure_shaped=False)
    before_rank = [f["file"] for f in before["files"]].index("SUBSTRATE") + 1

    after = embed_router.route(tmp_path, net, "voice store missing", backend=HashBackend())
    after_files = [f["file"] for f in after["files"]]
    after_rank = after_files.index("SUBSTRATE") + 1

    assert before_rank > 3                          # the defect, reproduced (also pinned above)
    assert after_rank <= 3                          # the fix: rank improves into the top-3
    assert after_rank < before_rank

    # the expansion's own bookkeeping: the rephrase is echoed, and the recovered hit is marked
    # with the variant that actually surfaced it hotter.
    assert after["failure_shape_expansion"] == (
        "where does voice store live / how is voice store provisioned")
    sub_hit = next(f for f in after["files"] if f["file"] == "SUBSTRATE")
    assert sub_hit["why"]["surfaced_by"] == "expanded"


def test_expansion_is_a_noop_on_neutral_queries(tmp_path: Path):
    """No behaviour change when the detector doesn't fire: a neutral phrasing of the SAME
    need (already correct per the audit) returns byte-for-byte the same record whether
    expansion is wired on or off, and carries none of the expansion's additive keys."""
    net = _voice_incident_net()
    goal = "where do voice exemplars live"
    on = embed_router.route(tmp_path, net, goal, backend=HashBackend())
    off = embed_router.route(tmp_path, net, goal, backend=HashBackend(),
                             expand_failure_shaped=False)
    assert on == off
    assert "failure_shape_expansion" not in on
    assert all("surfaced_by" not in f["why"] for f in on["files"])
    assert [f["file"] for f in on["files"]].index("SUBSTRATE") == 0   # still ranks 1st, untouched


def test_expansion_only_adds_to_the_pool_never_shrinks_it(tmp_path: Path):
    """The merge is additive by construction (max-score-per-candidate): every node the
    un-expanded descent reached is still reached after expansion turns on - expansion can
    promote a hit's score/rank, it cannot make a reachable node vanish."""
    net = _voice_incident_net()
    goal = "voice wash unavailable"
    off = embed_router.route(tmp_path, net, goal, backend=HashBackend(),
                             expand_failure_shaped=False)
    on = embed_router.route(tmp_path, net, goal, backend=HashBackend())
    off_ids = {f["file"] for f in off["files"]}
    on_ids = {f["file"] for f in on["files"]}
    assert off_ids <= on_ids


# --- WO-20260817-learned-keywords-selfheal: the projection self-heals at the consumer ---

def test_learned_keywords_rebuild_from_the_tracked_ledger_when_absent(tmp_path: Path):
    """THE FRESH-CLONE CASE. .learned_keywords.json is gitignored (it does not travel); the
    verdicts it projects DO travel. Before this cure the consumer returned {} and the accepted
    wires never reached the built network — and the close's own deposit skips the rebuild in
    exactly this case (the frontier is empty because every proposal is already judged)."""
    embed_router.bank_verdicts(tmp_path, [
        {"query": "the weld covenant", "id": "EIGEN_DIARY.md::33", "verdict": "wire", "why": "real"},
    ])
    proj = tmp_path / embed_router.LEARNED_KEYWORDS_FILE
    assert (tmp_path / embed_router.VERDICTS_FILE).is_file()
    proj.unlink()                                    # the fresh clone: verdicts yes, projection no

    learned = embed_router.load_learned_keywords(tmp_path)

    assert learned.get("EIGEN_DIARY.md::33"), "the consumer must rebuild from the tracked ledger"
    assert "weld" in learned["EIGEN_DIARY.md::33"]
    assert not proj.exists(), "the consumer reconstructs in memory without implicit publication"
    assert embed_router.load_learned_keywords(tmp_path) == learned   # second call: plain read


def test_learned_keywords_absent_ledger_still_returns_empty(tmp_path: Path):
    """No verdicts to project => the old empty answer, no file created. The self-heal fires on
    an absent PROJECTION with a present LEDGER, never conjures a ledger."""
    assert embed_router.load_learned_keywords(tmp_path) == {}
    assert not (tmp_path / embed_router.LEARNED_KEYWORDS_FILE).exists()


# ---------------------------------------------------------------------------
# the frontier mass term (WO-20260821-route-frontier-mass-term, 2026-08-21):
# the apex entered whole, the tie broken on evidence, and the pooling terms the
# sweep REFUTED kept as reachable modes so the refutation stays replayable.
# ---------------------------------------------------------------------------

def _ladder_net():
    """A file handle with a `::`-nested ladder under it, plus an independent rival."""
    nodes = {
        "root": {"id": "root", "grade": 2, "parent": None, "leaf": False,
                 "members": ["f.json", "rival.md"], "coverage": [], "keywords": []},
        "f.json": {"id": "f.json", "grade": 1, "parent": "root", "leaf": False,
                   "members": ["f.json::t", "f.json::u"], "coverage": [], "keywords": []},
        "f.json::t": {"id": "f.json::t", "grade": 0, "parent": "f.json", "leaf": True,
                      "members": [], "coverage": [], "keywords": []},
        "f.json::u": {"id": "f.json::u", "grade": 0, "parent": "f.json", "leaf": True,
                      "members": [], "coverage": [], "keywords": []},
        "rival.md": {"id": "rival.md", "grade": 0, "parent": "root", "leaf": True,
                     "members": [], "coverage": [], "keywords": []},
    }
    return nodes


def test_frontier_order_breaks_the_tie_on_evidence_not_the_alphabet():
    """Path inheritance collapses every sub-floor candidate onto EXACTLY the inherited value, so
    `(-heat, id)` hands the decision to spelling. `own` is already computed; it decides instead."""
    heat = {"aaa": 0.5, "zzz": 0.5}          # a perfect tie, as inheritance actually produces
    own = {"aaa": 0.1, "zzz": 0.4}           # zzz has the better claim of its own
    assert embed_router.frontier_order(["aaa", "zzz"], own, heat, {"tie_break": "own"}) \
        == ["zzz", "aaa"]
    assert embed_router.frontier_order(["aaa", "zzz"], own, heat, {"tie_break": "id"}) \
        == ["aaa", "zzz"]                    # the incumbent, still reachable and still alphabetical


def test_apex_is_entered_whole_and_the_beam_can_still_drop_it(tmp_path: Path):
    """LEVEL ZERO HAS NO HANDLE ABOVE IT TO PRUNE ON. Measured cause of three of route's four
    bench misses: 9 lens branches against a beam of 8, the drop decided by spelling."""
    nodes = {"root": {"id": "root", "grade": 2, "parent": None, "leaf": False,
                      "members": [f"L{i}" for i in range(4)], "coverage": [], "keywords": []}}
    for i in range(4):
        nodes[f"L{i}"] = {"id": f"L{i}", "grade": 1, "parent": "root", "leaf": False,
                          "members": [f"l{i}"], "coverage": [], "keywords": [],
                          "essence": f"lens {i} branch"}
        nodes[f"l{i}"] = {"id": f"l{i}", "grade": 0, "parent": f"L{i}", "leaf": True,
                          "members": [], "coverage": [], "keywords": [],
                          "essence": f"leaf under lens {i}"}
    net = {"nodes": nodes, "reach": {n: set() for n in nodes},
           "lenses": {n: ["engine"] for n in nodes}, "root": "root"}
    whole = embed_router.route(tmp_path, net, "leaf under lens 3", beam=1,
                               backend=HashBackend(), mass_policy={"apex": "whole"})
    pruned = embed_router.route(tmp_path, net, "leaf under lens 3", beam=1,
                                backend=HashBackend(), mass_policy={"apex": "beam"})
    assert whole["visited"] > pruned["visited"], "the whole apex reaches strictly more"
    assert all(f"l{i}" in {f["file"] for f in whole["files"]} for i in range(4))


def test_the_refuted_pooling_terms_are_still_reachable_and_do_what_they_say():
    """The sweep refuted these as a CURE (every one landed the incumbent's 23/25,
    evidence/ROUTE_MASS_TERM_2026-08-21/sweep.json). They stay as named modes so the refutation
    replays; these assertions pin what each one actually does to a pool."""
    nodes = _ladder_net()
    pool = {"f.json": 0.50, "f.json::t": 0.70, "f.json::u": 0.65, "rival.md": 0.55}
    own = dict(pool)
    heat = dict(pool)
    rank = embed_router.frontier_mass_rank
    inc = [n for n, _g, _r in rank(nodes, pool, own, heat, {"mode": "incumbent"}, floor=0.5)]
    assert inc == ["f.json::t", "f.json::u", "rival.md", "f.json"]
    q1 = [n for n, _g, _r in rank(nodes, pool, own, heat,
                                  {"mode": "handle_quota", "quota": 1}, floor=0.5)]
    assert q1 == ["f.json::t", "rival.md"], "one survivor per FILE handle, runners-up deleted"
    dec = rank(nodes, pool, own, heat, {"mode": "sibling_decay", "decay": 0.5}, floor=0.5)
    # `::u` is its parent's SECOND survivor, so it is attenuated toward the floor
    # (0.5 + 0.15*0.5 = 0.575) and still clears the rival at 0.55 - attenuated, not deleted.
    assert [n for n, _g, _r in dec] == ["f.json::t", "f.json::u", "rival.md", "f.json"]
    assert dec[1][1] < dec[1][2], "the attenuated hit reports both its adjusted and its raw heat"
    assert all(g >= 0.5 for _n, g, _r in dec), "attenuation contracts toward the floor, never below"


def test_mass_policy_rides_the_geometry_echo(tmp_path: Path):
    """view-equals-mechanism: the fire echoes the policy it actually ran with."""
    pol = {"mode": "sibling_decay", "decay": 0.8, "apex": "whole", "tie_break": "own"}
    rec = embed_router.route(tmp_path, _net(), "alpha particle physics",
                             backend=HashBackend(), mass_policy=pol)
    assert rec["geometry"]["mass_policy"] == pol


# ---------------------------------------------------------------------------
# the essence join - a served digest's claim rides the text the fold EMBEDS
# (RUL-20260823-essence-side-ratified; P25's mechanism)
# ---------------------------------------------------------------------------
#
# WHY THESE LIVE HERE and not beside the digest tests. `digest_lens` wires object referents into
# `reach`; `route` scores cosine over the vectors built from `node_text`, and reach never enters
# that dot - the gap P24 measured and named wired-is-not-routed. The join closes it in THIS
# module's composition, so this module's shard is where it is pinned.


def _digest_row(nodes: dict, nid: str, **over):
    """A conforming banked row for `nid` against the CURRENT membership - the shape
    `digest_lens.serve` calls `exact`. Overrides let each test break exactly one clause."""
    from laplace.engine import digest_mint
    members = digest_mint.leaf_members(nodes, nid)
    row = {"schema": "digest/0.1", "node_id": nid, "member_sha": digest_mint.member_sha(members),
           "basis": "b0", "grade": "claim", "method": "extracted",
           "claim": "The alpha cluster collects scattering and decay-chain notes, nothing else.",
           "object_tokens": [{"class": "snake", "token": "alpha_decay", "n": 4},
                             {"class": "upper", "token": "MeV", "n": 2}],
           "src_pointers": [["a1", 3]], "members": members}
    row.update(over)
    return row


def _bank(repo_root: Path, *rows) -> None:
    from laplace.engine import digest_mint
    (repo_root / digest_mint.DIGEST_STORE).write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


import pytest as _pytest


@_pytest.fixture()
def _armed_join(monkeypatch):
    """The RULED default is OFF until P25's verdict banks (the P26 confound-guard cure,
    NOTE-20260823-essence-wave-scope-breach): these tests exercise the join MECHANISM and
    arm it explicitly; test_the_join_defaults_off pins the default itself."""
    monkeypatch.setenv("LAPLACE_DIGEST_ESSENCE", "1")


def test_the_join_defaults_off_until_the_p25_verdict_banks(monkeypatch):
    """Guard (a) in code: unset, '0', and every non-'1' string serve the incumbent; a
    STRIP-EQUALS-'1' arms (the judge's letter-nit: ' 1' padded also arms - the switch
    strips before comparing, and this test's words now say what the code does). The
    default flips ON as the landing's own act, post-verdict."""
    monkeypatch.delenv("LAPLACE_DIGEST_ESSENCE", raising=False)
    assert embed_router.digest_essence_on() is False
    for bad in ("0", "on", "true", "yes", "2", ""):
        monkeypatch.setenv("LAPLACE_DIGEST_ESSENCE", bad)
        assert embed_router.digest_essence_on() is False, bad
    monkeypatch.setenv("LAPLACE_DIGEST_ESSENCE", "1")
    assert embed_router.digest_essence_on() is True


def test_a_served_digest_joins_the_embedded_text_marked(tmp_path: Path, _armed_join):
    """The join itself: original + the MARKER + claim + " | " + the banked object tokens. The
    marker is condition (i) - a served claim is visible as served and never masquerades as the
    node's own prose - and the block is `digest_mint.digest_text`, the SAME one line the meter
    queries with and the lens mints referents from. One derivation, so the thing measured, the
    thing wired and the thing embedded cannot drift into three."""
    from laplace.engine import digest_mint

    net = _net()
    row = _digest_row(net["nodes"], "A")
    _bank(tmp_path, row)

    txt = embed_router.node_text(tmp_path, net, "A")
    base, marker, block = txt.partition(embed_router.DIGEST_MARKER)

    assert marker == embed_router.DIGEST_MARKER == " [digest] "
    assert block == digest_mint.digest_text(row).strip()
    assert block.startswith(row["claim"] + " | ")
    assert "alpha_decay MeV" in block
    # the ORIGINAL half is untouched - the join only ever ADDS, the same additivity discipline
    # digest_lens' own guard holds to
    assert base == embed_router.node_text(tmp_path, {**net, "nodes": net["nodes"]}, "A",
                                          digests={})
    assert base.startswith("A | root | engine | the alpha cluster")


def test_the_switch_off_is_byte_identical_and_reads_no_store(tmp_path: Path, monkeypatch):
    """Condition (iv), the null arm's lever. `LAPLACE_DIGEST_ESSENCE=0` disables the join
    COMPLETELY: not a marker with an empty block, not a trailing space - the exact string the
    composition produced before the join existed, for every node, whether or not it has a row.
    Byte-identity is what makes the null arm a null arm; anything else and the arm measures the
    join's formatting as well as its content."""
    net = _net()
    _bank(tmp_path, _digest_row(net["nodes"], "A"))

    monkeypatch.setenv("LAPLACE_DIGEST_ESSENCE", "0")
    assert embed_router.digest_essence_on() is False
    off = {nid: embed_router.node_text(tmp_path, net, nid) for nid in net["nodes"]}
    assert embed_router.digest_essences(tmp_path, net) == {}

    # the same composition with no store on disk at all IS the pre-join composition
    monkeypatch.delenv("LAPLACE_DIGEST_ESSENCE", raising=False)
    (tmp_path / ".digests.jsonl").unlink()
    bare = {nid: embed_router.node_text(tmp_path, net, nid) for nid in net["nodes"]}

    assert off == bare
    assert not any(embed_router.DIGEST_MARKER in t for t in off.values())


def test_only_a_conforming_row_may_join(tmp_path: Path):
    """The read-side law is re-applied at the EMBEDDED boundary, not just the wired one. A
    hand-appended `composed` row with no pointers was PROVEN to mint `digest::fabricated` into
    reach; the same row must not be able to put fabricated prose into a node's vector either. Each
    clause is broken one at a time and named by `digest_lens.conformance`."""
    from laplace.engine import digest_lens

    net = _net()
    cases = {
        "composed-without-src-pointers": _digest_row(net["nodes"], "A", method="composed",
                                                     src_pointers=[]),
        "no-src-pointers": _digest_row(net["nodes"], "A", src_pointers=[]),
        "empty-claim": _digest_row(net["nodes"], "A", claim="   "),
        "method-not-extracted-or-composed": _digest_row(net["nodes"], "A", method="handwritten"),
    }
    for reason, row in cases.items():
        _bank(tmp_path, row)
        assert digest_lens.conformance(row) == reason, reason
        assert embed_router.digest_essences(tmp_path, net) == {}, reason
        assert embed_router.DIGEST_MARKER not in embed_router.node_text(tmp_path, net, "A"), reason


def test_a_stale_row_never_joins(tmp_path: Path):
    """A digest of a membership the node no longer has would embed what the node USED to hold -
    the imitated-continuity failure the whole layer exists against. Below the drift floor the row
    is `stale`, and stale is not in SERVING, so it reaches neither reach nor the vector."""
    from laplace.engine import digest_lens

    net = _net()
    row = _digest_row(net["nodes"], "A", member_sha="deadbeef",
                      members=["gone1", "gone2", "gone3", "gone4", "gone5"])
    _bank(tmp_path, row)

    assert digest_lens.serve(net["nodes"], [row])["A"]["status"] == "stale"
    assert embed_router.digest_essences(tmp_path, net) == {}
    assert embed_router.DIGEST_MARKER not in embed_router.node_text(tmp_path, net, "A")


def test_the_join_moves_the_content_hash_so_the_node_re_embeds(tmp_path: Path, _armed_join):
    """wired-is-ROUTED, mechanically: the joined text is what gets hashed and embedded, so a node
    that gains a serving digest goes stale and re-embeds with claim-grade content in its vector.
    If the join did not reach the hash it would be decoration."""
    net, b = _net(), HashBackend()
    before = embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)
    assert before["n_embedded"] == len(net["nodes"])

    _bank(tmp_path, _digest_row(net["nodes"], "A"))
    after = embed_router.ensure_embeddings(tmp_path, net, b, bulk=True)

    assert after["n_embedded"] == 1, "exactly the served node re-embeds; its siblings are cached"
    assert after["vectors"]["A"] != before["vectors"]["A"]
    assert after["vectors"]["b1"] == before["vectors"]["b1"]


def test_the_basis_memo_refuses_a_freshly_minted_digest_store(tmp_path: Path, _armed_join):
    """The one forbidden failure, on the join's new input. `.digests.jsonl` is the SECOND node_text
    input on disk (the folded soul shard is the first): a mint moves the embedded text of every
    node it serves while `net` and the vector store sit still. Without the stat in `_basis_key` the
    memo would hand a caller pre-mint vectors and call them fresh."""
    net, b = _net(), HashBackend()
    first = embed_router.basis(tmp_path, net, b)
    assert embed_router.basis(tmp_path, net, b) is first, "unmoved inputs memoise"

    _bank(tmp_path, _digest_row(net["nodes"], "A"))
    second = embed_router.basis(tmp_path, net, b)

    assert second is not first, "a fresh mint must invalidate the memo"
    assert list(second["vectors"]["A"]) != list(first["vectors"]["A"])


def test_flipping_the_switch_invalidates_the_memo_so_the_arms_never_share(tmp_path: Path, monkeypatch, _armed_join):
    """The null arm is measured by flipping `LAPLACE_DIGEST_ESSENCE` in a live process, so the two
    arms must never share a memo slot - a shared slot would silently score arm 1's vectors as arm
    0's and the whole G3 comparison would be one arm measured twice."""
    net, b = _net(), HashBackend()
    _bank(tmp_path, _digest_row(net["nodes"], "A"))

    on = embed_router.basis(tmp_path, net, b)
    monkeypatch.setenv("LAPLACE_DIGEST_ESSENCE", "0")
    off = embed_router.basis(tmp_path, net, b)

    assert off is not on
    assert list(off["vectors"]["A"]) != list(on["vectors"]["A"])


def test_the_join_reaches_the_cosine_route_actually_scores(tmp_path: Path):
    """THE DESIGN'S OWN CLAIM, pinned: wired-is-ROUTED by construction. `digest_lens` mints object
    referents into `reach`, and `reach` never enters route's dot product - that is the gap P24
    measured. Here a query built from the CLAIM's vocabulary alone (words the node's label,
    essence, keywords and coverage do not contain) reaches the served node only once the join is
    armed. If this ever goes green in both arms the join has stopped being the mechanism."""
    net = _net()
    claim = ("Hafnium oxide memristor crossbars anneal into filamentary conduction "
             "under a compliance-limited forming sweep.")
    _bank(tmp_path, _digest_row(net["nodes"], "A", claim=claim,
                                object_tokens=[{"class": "snake", "token": "memristor_forming",
                                                "n": 7}]))
    goal = "hafnium oxide memristor filamentary conduction"

    def heat(digests_on: bool) -> float:
        embed_router._DIGEST_MEMO.clear()
        import os
        prev = os.environ.get("LAPLACE_DIGEST_ESSENCE")
        os.environ["LAPLACE_DIGEST_ESSENCE"] = "1" if digests_on else "0"
        try:
            b = HashBackend()
            basis = embed_router.basis(tmp_path, net, b, bulk=True)
            import math
            q = b.query(goal)
            v = basis["vectors"]["A"]
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            return sum(qi * vi for qi, vi in zip(q, v, strict=True)) / n
        finally:
            if prev is None:
                os.environ.pop("LAPLACE_DIGEST_ESSENCE", None)
            else:
                os.environ["LAPLACE_DIGEST_ESSENCE"] = prev

    off, on = heat(False), heat(True)
    assert on > off, f"the joined claim must move the routed cosine (off={off:.4f} on={on:.4f})"


# ---------------------------------------------------------------------------
# the drip's named orderer (WO-20260820-graded-serving-drip)
# ---------------------------------------------------------------------------

def test_drip_order_spends_apex_first_lens_first():
    """A budgeted drip must warm the nodes a descent touches earliest: the root, then its
    members (the lenses), then each deeper ring - never a lexicographic prefix. 'Z-root'
    sorts lexicographically LAST here, so the flat sort this replaced would starve it."""
    nodes = {
        "Z-root": {"id": "Z-root", "parent": None, "leaf": False, "members": ["M", "A"]},
        "M": {"id": "M", "parent": "Z-root", "leaf": False, "members": ["m2", "m1"]},
        "A": {"id": "A", "parent": "Z-root", "leaf": False, "members": ["a1"]},
        "m1": {"id": "m1", "parent": "M", "leaf": True, "members": []},
        "m2": {"id": "m2", "parent": "M", "leaf": True, "members": []},
        "a1": {"id": "a1", "parent": "A", "leaf": True, "members": []},
        "orphan": {"id": "orphan", "parent": None, "leaf": True, "members": []},
    }
    net = {"nodes": nodes, "root": "Z-root"}
    ordered = embed_router._drip_order(net, list(nodes))
    # ring 0: the apex; ring 1: the lenses (id-tied inside the ring); ring 2: the leaves;
    # unreachable last. A budget prefix of any size now cuts along descent depth.
    assert ordered == ["Z-root", "A", "M", "a1", "m1", "m2", "orphan"]


def test_drip_order_is_deterministic_and_total():
    """Same stale set in any input order -> same output; every input id survives (the drip
    may defer nodes, never lose them)."""
    nodes = {
        "root": {"id": "root", "parent": None, "leaf": False, "members": ["B", "A"]},
        "A": {"id": "A", "parent": "root", "leaf": True, "members": []},
        "B": {"id": "B", "parent": "root", "leaf": True, "members": []},
    }
    net = {"nodes": nodes, "root": "root"}
    fwd = embed_router._drip_order(net, ["A", "B", "root"])
    rev = embed_router._drip_order(net, ["root", "B", "A"])
    assert fwd == rev == ["root", "A", "B"]


# ---------------------------------------------------------------------------
# the store write lock (WO-20260819-embeddings-store-write-lock, STORE-01)
# ---------------------------------------------------------------------------

def test_contended_store_write_degrades_but_plain(tmp_path: Path, monkeypatch):
    """On StoreBusy the serving call must serve its in-memory result UNPERSISTED and never
    block or raise - the next successful call's write catches up (STORE-01's contention arm)."""
    import contextlib

    from laplace.pipeline import locking

    @contextlib.contextmanager
    def busy(name, timeout=20.0):
        raise locking.StoreBusy(f"contended: {name}")
        yield  # pragma: no cover

    monkeypatch.setattr(locking, "store_lock", busy)
    net = _net()
    b = HashBackend()
    result = embed_router.ensure_embeddings(tmp_path, net, b)
    assert result["n_embedded"] == len(net["nodes"])          # the work still happened
    assert len(result["vectors"]) == len(net["nodes"])        # ...and serves in-memory
    assert not (tmp_path / CACHE_FILE).is_file()              # ...but nothing persisted

    monkeypatch.undo()                                        # contention clears

    third = embed_router.ensure_embeddings(tmp_path, net, b)
    assert (tmp_path / CACHE_FILE).is_file()                  # the next successful call banked
    assert third["n_cached"] + third["n_embedded"] == len(net["nodes"])


def test_release_backend_drops_process_owner_and_calls_close(monkeypatch):
    class Backend:
        gpu=True;providers=['CUDAExecutionProvider','CPUExecutionProvider']
        def __init__(self):self.closed=False
        def close(self):self.closed=True
    backend=Backend();monkeypatch.setattr(embed_router,'_BACKEND',backend)

    receipt=embed_router.release_backend(backend)

    assert receipt=={'released':True,'gpu':True,
                     'providers':['CUDAExecutionProvider','CPUExecutionProvider']}
    assert backend.closed is True and embed_router._BACKEND is None


def test_get_backend_constructs_and_caches_after_release_seam(monkeypatch):
    backend=object()
    monkeypatch.setattr(embed_router,'_BACKEND',None)
    monkeypatch.setattr(embed_router,'_BACKEND_FAILED',False)
    monkeypatch.setattr(embed_router,'FastEmbedBackend',lambda:backend)
    assert embed_router.get_backend() is backend
    assert embed_router.get_backend() is backend


def test_fastembed_close_releases_owned_model_reference():
    import gc,weakref
    class Model:pass
    model=Model();observed=weakref.ref(model)
    backend=embed_router.FastEmbedBackend.__new__(embed_router.FastEmbedBackend)
    backend._model=model
    del model

    backend.close();gc.collect()

    assert backend._model is None and observed() is None
