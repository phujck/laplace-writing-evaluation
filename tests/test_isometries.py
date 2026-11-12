"""The organ's store shard (v1 M2/M3): writer, reader, meter, guard, and the IO-only clause.

Every test here is a rider's unit witness: R1 (degenerate-handle refusal), R2's tolerance
(orthonormality at the selftest bar), the written-but-unread selftest itself, constraint (b)
(raw-norm meter, margin scales with the signal), the flag-off inertness (M2's IO-only
clause at unit level - the byte-identity fold run is CP-2's separate acceptance), and the
rebuild path (rider R3's command, exercised on a synthetic persisted tree)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from laplace.representation import isometries


def _rng(seed=7):
    return np.random.default_rng(seed)


def _block(n=12, d=16, seed=7):
    X = _rng(seed).normal(size=(n, d)).astype(np.float32)
    X += 0.5  # keep the mean's norm comfortably above the degenerate bar
    return X


# ---------------------------------------------------------------------------
# the frame math
# ---------------------------------------------------------------------------

def test_block_frame_first_column_is_the_normalized_mean():
    X = _block()
    frame, refusal = isometries.block_frame(X, chi=4)
    assert refusal is None
    mu = X.mean(axis=0)
    h = mu / np.linalg.norm(mu)
    # QR may flip sign; the span is the claim
    assert min(np.linalg.norm(frame["Q"][:, 0] - h),
               np.linalg.norm(frame["Q"][:, 0] + h)) < 1e-5


def test_block_frame_is_orthonormal_at_the_selftest_bar():
    X = _block(n=20, d=32)
    frame, _ = isometries.block_frame(X, chi=8)
    Q = frame["Q"]
    err = np.abs(Q.T @ Q - np.eye(Q.shape[1], dtype=np.float32)).max()
    assert err < isometries.SELFTEST_TOL


def test_block_frame_chi_clamps_like_the_rho_cell():
    X = _block(n=3, d=16)                       # n-1 = 2 caps extra at 2 -> 3 columns total
    frame, _ = isometries.block_frame(X, chi=8)
    assert frame["Q"].shape[1] == 3


def test_degenerate_handle_is_refused_with_a_typed_reason():
    """Rider R1: the rho cell's scratch guard is load-bearing once banked - a block whose
    mean has no direction refuses, never banks a near-zero first column silently."""
    X = np.zeros((4, 8), dtype=np.float32)
    X[0, 0], X[1, 0] = 1.0, -1.0                # mean exactly zero, block not empty
    frame, refusal = isometries.block_frame(X, chi=4)
    assert frame is None
    assert refusal["reason"] == "degenerate-handle"
    assert refusal["norm"] <= isometries.DEGENERATE_NORM


# ---------------------------------------------------------------------------
# the meter (constraint b)
# ---------------------------------------------------------------------------

def test_residual_is_the_raw_norm_and_margin_scales_with_the_signal():
    X = _block()
    frame, _ = isometries.block_frame(X, chi=4)
    x = _rng(11).normal(size=X.shape[1]).astype(np.float32)
    r1 = isometries.residual(x, frame["Q"])
    r2 = isometries.residual(2.0 * x, frame["Q"])
    assert r1 > 0
    assert abs(r2 - 2.0 * r1) < 1e-3            # no normalization flattens the margin


def test_residual_is_zero_inside_the_subspace():
    X = _block()
    frame, _ = isometries.block_frame(X, chi=4)
    inside = frame["Q"] @ _rng(3).normal(size=frame["Q"].shape[1]).astype(np.float32)
    assert isometries.residual(inside, frame["Q"]) < 1e-4


# ---------------------------------------------------------------------------
# the store: write, selftest, read
# ---------------------------------------------------------------------------

def test_write_read_round_trip_with_selftest(tmp_path: Path):
    X = _block()
    report = isometries.write_at_fold(tmp_path, {"concept::aa": (X, 1, 16)})
    assert report["persisted"] and report["selftest"]["pass"]
    got = isometries.read_for_descent(tmp_path)
    f = got["frames"]["concept::aa"]
    assert f["level"] == 1 and f["chi"] == 16 and f["n"] == len(X)
    assert got["meta"]["rebuild_cmd"] == isometries.REBUILD_CMD   # the rider travels in-store


def test_write_merges_and_refusals_are_typed_rows_in_meta(tmp_path: Path):
    isometries.write_at_fold(tmp_path, {"concept::aa": (_block(seed=1), 1, 16)})
    Xz = np.zeros((4, 16), dtype=np.float32)
    Xz[0, 0], Xz[1, 0] = 1.0, -1.0
    report = isometries.write_at_fold(
        tmp_path, {"concept::bb": (_block(seed=2), 2, 8), "concept::zz": (Xz, 2, 8)})
    assert report["banked"] == ["concept::bb"]
    assert report["refused"][0]["block"] == "concept::zz"
    got = isometries.read_for_descent(tmp_path)
    assert set(got["frames"]) == {"concept::aa", "concept::bb"}   # merge kept the first write
    assert any(r["block"] == "concept::zz" and r["reason"] == "degenerate-handle"
               for r in got["meta"]["refused"])


def test_absent_store_reads_empty_never_raises(tmp_path: Path):
    got = isometries.read_for_descent(tmp_path)
    assert got["frames"] == {} and "absent" in got["meta"]


def test_contended_write_degrades_but_plain(tmp_path: Path, monkeypatch):
    import contextlib

    from laplace.pipeline import locking

    @contextlib.contextmanager
    def busy(name, timeout=20.0):
        raise locking.StoreBusy(name)
        yield  # pragma: no cover

    monkeypatch.setattr(locking, "store_lock", busy)
    report = isometries.write_at_fold(tmp_path, {"concept::aa": (_block(), 1, 16)})
    assert not report["persisted"] and "store-busy" in report["why_unpersisted"]
    assert not (tmp_path / isometries.STORE).is_file()


# ---------------------------------------------------------------------------
# the collector seam: flag-inert (M2's IO-only clause at unit level)
# ---------------------------------------------------------------------------

def test_collector_is_inert_without_the_flag(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("LAPLACE_ORGAN_V1", raising=False)
    with isometries.collect(tmp_path):
        isometries.note_block("concept::aa", _block(), level=1, chi=16)
    assert not (tmp_path / isometries.STORE).is_file()


def test_collector_banks_at_scope_exit_under_the_flag(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LAPLACE_ORGAN_V1", "1")
    with isometries.collect(tmp_path):
        isometries.note_block("concept::aa", _block(seed=1), level=1, chi=16)
        isometries.note_block("concept::bb", _block(seed=2), level=2, chi=8)
        assert not (tmp_path / isometries.STORE).is_file()   # one write, at exit, not per note
    got = isometries.read_for_descent(tmp_path)
    assert set(got["frames"]) == {"concept::aa", "concept::bb"}
    assert got["meta"]["source"] == "fold"


def test_note_block_outside_any_scope_is_a_noop(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LAPLACE_ORGAN_V1", "1")
    isometries.note_block("concept::aa", _block(), level=1, chi=16)   # no scope open
    assert not (tmp_path / isometries.STORE).is_file()


# ---------------------------------------------------------------------------
# the rebuild (rider R3's command, on a synthetic persisted tree)
# ---------------------------------------------------------------------------

def test_rebuild_from_persisted_tree_matches_direct_write(tmp_path: Path):
    d = 16
    rng = _rng(5)
    leaves = {f"leaf{i}": (rng.normal(size=d) + 0.5).astype(np.float32) for i in range(8)}
    ids = sorted(leaves)
    X = np.stack([leaves[n] for n in ids])
    np.save(tmp_path / ".meaning_vectors.f32.npy", X)
    (tmp_path / ".meaning_vectors.index.json").write_text(json.dumps(
        {"format": "meaning-vectors-sidecar/1", "ids": ids,
         "vectors": ".meaning_vectors.f32.npy"}))
    # root -> A {leaf0..3}, B {leaf4..7}; B -> B1 {leaf4,5} (depth 2)
    tree = {"version": "t", "root_id": "mind://", "lens_hash": "", "lens_pairs": [],
            "clusters": {"A": {"members": ids[:4]}, "B": {"members": ["B1"] + ids[6:]},
                         "B1": {"members": ids[4:6]}},
            "parent_map": {**{n: "A" for n in ids[:4]},
                           **{n: "B1" for n in ids[4:6]},
                           **{n: "B" for n in ids[6:]},
                           "A": "mind://", "B": "mind://", "B1": "B"},
            "leaf_sha": {}}
    (tmp_path / ".meaning_tree.json").write_text(json.dumps(tree))

    report = isometries.rebuild(tmp_path)
    assert report["persisted"] and report["counts"]["banked"] == 3
    got = isometries.read_for_descent(tmp_path)
    assert got["frames"]["A"]["level"] == 1 and got["frames"]["A"]["chi"] == 16
    assert got["frames"]["B1"]["level"] == 2 and got["frames"]["B1"]["chi"] == 8
    # the rebuild's frame IS the direct write's frame on the same block (one math, one object)
    direct, _ = isometries.block_frame(X[:4], chi=16)
    assert np.allclose(got["frames"]["A"]["Q"], direct["Q"], atol=1e-6)


# ---------------------------------------------------------------------------
# M2's IO-only clause at FOLD level (rider R2's byte-identity, fixture-scoped):
# the incumbent fold ARTIFACT stores are hash-identical with the flag off vs on;
# the flag adds exactly one new store. Row ledgers (residue rows) are excluded by
# name: they wear the one-stamp law's UTC stamps and are not fold artifacts.
# ---------------------------------------------------------------------------

def _fake_backend_cls():
    import hashlib

    class FakeBackend:
        name = "fake:organ-io-test"
        FAMILIES = {"alpha": 0, "beta": 1, "gamma": 2}
        dim = 6

        def _vec(self, text):
            base = [0.0] * self.dim
            fam = 0
            for k, idx in self.FAMILIES.items():
                if k in text:
                    fam = idx
                    base[idx] = 1.0
                    break
            h = int(hashlib.sha1(text.encode()).hexdigest(), 16)
            base[(fam + 3) % self.dim] += (h % 100) / 1000.0
            n = sum(x * x for x in base) ** 0.5
            return [x / n for x in base] if n else base

        def embed(self, texts):
            return [self._vec(t) for t in texts]

        def query(self, text):
            return self._vec(text)

    return FakeBackend


ARTIFACT_GLOBS = (".meaning_tree.json", ".meaning_vectors.f32.npy",
                  ".meaning_vectors.index.json")


def _run_fold(root: Path, monkeypatch, flag: bool):
    import hashlib

    from laplace.representation import embed_router
    from laplace.engine import meaning_upfold
    monkeypatch.setattr(embed_router, "get_backend", lambda: _fake_backend_cls()())
    if flag:
        monkeypatch.setenv("LAPLACE_ORGAN_V1", "1")
    else:
        monkeypatch.delenv("LAPLACE_ORGAN_V1", raising=False)
    residue = {}
    for fam in ("alpha", "beta", "gamma"):
        for i in range(8):
            residue[f"{fam}/{fam}_{i}.md"] = {"kind": "md", "essence": fam,
                                              "keywords": [fam, f"{fam}{i}"], "sealed": False}
    root.mkdir(parents=True, exist_ok=True)
    meaning_upfold.cluster_residue_incremental(root, residue, None, lens_hash="L0")
    hashes = {}
    for name in ARTIFACT_GLOBS:
        p = root / name
        if p.is_file():
            hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


def test_fold_artifacts_byte_identical_flag_off_vs_on(tmp_path: Path, monkeypatch):
    off1 = _run_fold(tmp_path / "off1", monkeypatch, flag=False)
    off2 = _run_fold(tmp_path / "off2", monkeypatch, flag=False)
    assert off1 == off2, "the fold itself must be deterministic for byte-identity to mean anything"
    on = _run_fold(tmp_path / "on", monkeypatch, flag=True)
    assert on == off1, "the flag must not move a single incumbent artifact byte"
    assert not (tmp_path / "off1" / isometries.STORE).is_file()
    assert (tmp_path / "on" / isometries.STORE).is_file()          # the one additive store
    got = isometries.read_for_descent(tmp_path / "on")
    assert got["frames"], "the flagged fold banked frames"
    assert all(v["chi"] in (16, 8) for v in got["frames"].values())


# ---------------------------------------------------------------------------
# the judge's CP-2 defects, pinned (D2 torn-store, D3 ladder cross-pin, D4 retirement)
# ---------------------------------------------------------------------------

def test_torn_store_serves_typed_empty_and_the_writer_heals(tmp_path: Path):
    """D2: a torn npz serves {frames: {}, meta: {torn: ...}} - never raises (the read is
    route-load-bearing at M4); and a write over the torn store heals it."""
    (tmp_path / isometries.STORE).write_bytes(b"not an npz at all")
    got = isometries.read_for_descent(tmp_path)
    assert got["frames"] == {} and "torn" in got["meta"]
    report = isometries.write_at_fold(tmp_path, {"concept::aa": (_block(), 1, 16)})
    assert report["persisted"] and report["selftest"]["pass"]
    healed = isometries.read_for_descent(tmp_path)
    assert set(healed["frames"]) == {"concept::aa"}


def test_write_is_atomic_no_partial_store_no_stray_temp(tmp_path: Path):
    """D2: the write goes temp -> fsync -> os.replace; after a successful write no temp
    remains and the store loads whole."""
    isometries.write_at_fold(tmp_path, {"concept::aa": (_block(), 1, 16)})
    assert not list(tmp_path.glob("*.tmp"))
    assert isometries.read_for_descent(tmp_path)["frames"]


def test_ladder_cross_pin_rebuild_matches_the_fold_declaration():
    """D3: rebuild's numeric ladder restates meaning_upfold's declared one - this pin
    asserts equality over levels 1..10 so the two homes cannot drift apart silently."""
    from laplace.engine.meaning_upfold import _selector_chi

    # reach the closure's ladder through a probe rebuild? No - the ladder fn is module
    # scope inside rebuild; pin the DECLARED values through a minimal rebuild fixture
    # is heavy, so the pin reads both homes directly:
    import inspect

    from laplace.representation import isometries as iso
    src = inspect.getsource(iso.rebuild)
    assert "16 if level <= 1 else 8" in src, "rebuild's ladder text moved - re-pin against the declaration"
    for level in range(1, 11):
        declared = _selector_chi(level)
        restated = 16 if level <= 1 else 8
        assert restated == declared, f"ladder drift at level {level}: {restated} != {declared}"


def test_refusal_retires_when_the_block_banks_clean(tmp_path: Path):
    """D4: refusals are per-block state, not an append log - a block that later banks
    clean retires its refusal; a re-refused block carries ONE current row."""
    Xz = np.zeros((4, 16), dtype=np.float32)
    Xz[0, 0], Xz[1, 0] = 1.0, -1.0
    isometries.write_at_fold(tmp_path, {"concept::aa": (Xz, 1, 16)})
    got = isometries.read_for_descent(tmp_path)
    assert [r["block"] for r in got["meta"]["refused"]] == ["concept::aa"]
    isometries.write_at_fold(tmp_path, {"concept::aa": (Xz, 1, 16)})      # re-refused: one row
    assert len(isometries.read_for_descent(tmp_path)["meta"]["refused"]) == 1
    isometries.write_at_fold(tmp_path, {"concept::aa": (_block(), 1, 16)})  # banks clean
    got = isometries.read_for_descent(tmp_path)
    assert got["meta"]["refused"] == [] and "concept::aa" in got["frames"]


# ---------------------------------------------------------------------------
# M4 - route consumption of banked frames (behind BOTH flags), causes counted
# ---------------------------------------------------------------------------

def _route_net(widths):
    nodes = {"root": {"id": "root", "grade": 2, "parent": None, "leaf": False,
                      "members": list(widths), "coverage": [], "keywords": [],
                      "essence": "the root of the synthetic world"}}
    for branch, n in widths.items():
        nodes[branch] = {"id": branch, "grade": 1, "parent": "root", "leaf": False,
                         "members": [f"{branch}{i}" for i in range(n)],
                         "coverage": [], "keywords": [branch],
                         "essence": f"the {branch} cluster of the synthetic world"}
        for i in range(n):
            nodes[f"{branch}{i}"] = {"id": f"{branch}{i}", "grade": 0, "parent": branch,
                                     "leaf": True, "members": [], "coverage": [],
                                     "keywords": [branch],
                                     "essence": f"{branch} member {i} - scattering decay {i}"}
    return {"nodes": nodes, "reach": {k: set() for k in nodes},
            "lenses": {k: ["engine"] for k in nodes}, "root": "root"}


def _bank_frame_for(tmp_path, net, nid, backend, chi=8):
    from laplace.representation import embed_router
    vecs = embed_router.ensure_embeddings(tmp_path, net, backend)["vectors"]
    import numpy as _np
    kids = [m for m in net["nodes"][nid]["members"] if m in vecs]
    mat = _np.stack([_np.asarray(vecs[k], dtype=_np.float32) for k in kids])
    return isometries.write_at_fold(tmp_path, {nid: (mat, 1, chi)})


@pytest.fixture()
def organ_armed(monkeypatch):
    monkeypatch.setenv("LAPLACE_BLOCK_RENORM", "1")
    monkeypatch.setenv("LAPLACE_ORGAN_V1", "1")
    from laplace.representation import embed_router
    embed_router._ORGAN_MEMO.clear()
    yield
    embed_router._ORGAN_MEMO.clear()


def test_route_serves_banked_frames_and_names_the_venue(tmp_path: Path, organ_armed):
    from laplace.representation import embed_router
    from laplace.representation.embed_router import HashBackend
    net = _route_net({"a": 6, "b": 4})
    b = HashBackend()
    (tmp_path / ".meaning_tree.json").write_text("{}")   # the grounding tree, older than
    report = _bank_frame_for(tmp_path, net, "a", b)      # the frames banked after it
    assert report["persisted"]
    rec = embed_router.route(tmp_path, net, "a scattering decay", backend=b)
    org = rec["block_renorm"]["organ"]
    assert org["served"] >= 1                       # the banked frame served block 'a'
    assert org["fallback_by_cause"]["no_key"] >= 1  # root/b carry no frame, counted by cause
    assert "+organV1" in rec["router"]              # the venue says so (run-row law)


def test_route_without_organ_flag_is_untouched_by_the_store(tmp_path: Path, monkeypatch):
    from laplace.representation import embed_router
    from laplace.representation.embed_router import HashBackend
    monkeypatch.setenv("LAPLACE_BLOCK_RENORM", "1")
    monkeypatch.delenv("LAPLACE_ORGAN_V1", raising=False)
    embed_router._ORGAN_MEMO.clear()
    net = _route_net({"a": 6, "b": 4})
    b = HashBackend()
    monkeypatch.setenv("LAPLACE_ORGAN_V1", "1")     # bank under the flag...
    _bank_frame_for(tmp_path, net, "a", b)
    monkeypatch.delenv("LAPLACE_ORGAN_V1")           # ...then route without it
    rec = embed_router.route(tmp_path, net, "a scattering decay", backend=b)
    assert "organ" not in rec["block_renorm"]        # the arm never engaged


def test_route_counts_stale_isometry_when_the_tree_moved(tmp_path: Path, organ_armed):
    import time as _t

    from laplace.representation import embed_router
    from laplace.representation.embed_router import HashBackend
    net = _route_net({"a": 6})
    b = HashBackend()
    _bank_frame_for(tmp_path, net, "a", b)
    _t.sleep(0.02)
    (tmp_path / ".meaning_tree.json").write_text("{}")   # the tree is now newer than the frames
    embed_router._ORGAN_MEMO.clear()
    rec = embed_router.route(tmp_path, net, "a scattering decay", backend=b)
    org = rec["block_renorm"]["organ"]
    assert org["served"] == 0
    assert org["fallback_by_cause"]["stale_isometry"] >= 1


def test_route_counts_torn_store_and_still_serves(tmp_path: Path, organ_armed):
    from laplace.representation import embed_router
    from laplace.representation.embed_router import HashBackend
    net = _route_net({"a": 6})
    b = HashBackend()
    embed_router.ensure_embeddings(tmp_path, net, b)
    (tmp_path / isometries.STORE).write_bytes(b"garbage")
    rec = embed_router.route(tmp_path, net, "a scattering decay", backend=b)
    assert rec is not None and rec["files"]             # the route SERVED despite the torn store
    assert rec["block_renorm"]["organ"]["fallback_by_cause"]["torn"] >= 1


# ---------------------------------------------------------------------------
# the fork arm (NOTE-20260824-organ-residual-arm-prereg): frames as a margin-
# preserving within-block gate over untouched incumbent scores
# ---------------------------------------------------------------------------

@pytest.fixture()
def fork_armed(monkeypatch):
    monkeypatch.setenv("LAPLACE_ORGAN_V1", "1")
    monkeypatch.setenv("LAPLACE_ORGAN_RESIDUAL", "1")
    monkeypatch.delenv("LAPLACE_BLOCK_RENORM", raising=False)
    from laplace.representation import embed_router
    embed_router._ORGAN_MEMO.clear()
    yield
    embed_router._ORGAN_MEMO.clear()


def test_fork_arm_serves_report_and_venue_without_renorm(tmp_path: Path, fork_armed):
    from laplace.representation import embed_router
    from laplace.representation.embed_router import HashBackend
    net = _route_net({"a": 6, "b": 4})
    b = HashBackend()
    (tmp_path / ".meaning_tree.json").write_text("{}")
    _bank_frame_for(tmp_path, net, "a", b)
    rec = embed_router.route(tmp_path, net, "a scattering decay", backend=b)
    assert "+organR" in rec["router"] and "+blockR" not in rec["router"]
    assert "block_renorm" not in rec                      # the renorm arm never engaged
    r = rec["organ_residual"]
    assert r["blocks_gated"] >= 1                         # block 'a' was gated by its frame
    assert r["skipped_by_cause"]["no_key"] >= 1           # root/b carry no frame, counted


def test_fork_arm_untouched_when_flag_off(tmp_path: Path, monkeypatch):
    from laplace.representation import embed_router
    from laplace.representation.embed_router import HashBackend
    monkeypatch.setenv("LAPLACE_ORGAN_V1", "1")
    monkeypatch.delenv("LAPLACE_ORGAN_RESIDUAL", raising=False)
    embed_router._ORGAN_MEMO.clear()
    net = _route_net({"a": 6})
    b = HashBackend()
    (tmp_path / ".meaning_tree.json").write_text("{}")
    _bank_frame_for(tmp_path, net, "a", b)
    rec = embed_router.route(tmp_path, net, "a scattering decay", backend=b)
    assert "organ_residual" not in rec and "+organR" not in rec["router"]


def test_fork_arm_demotes_only_the_incoherent_and_keeps_margins(fork_armed):
    """The unit witness of the prereg's whole claim: kept children keep their global-cosine
    scores VERBATIM (the margin carrier untouched); only above-q90 residual children move,
    to just below the kept, order preserved among themselves."""
    import numpy as np

    from laplace.representation import embed_router

    rng = np.random.default_rng(3)
    d = 16
    Q, _ = np.linalg.qr(rng.normal(size=(d, 3)).astype(np.float32))
    Q = Q.astype(np.float32)
    # nine coherent children (inside span(Q), tiny residual) + one alien (orthogonal-ish)
    kids = {}
    for i in range(9):
        kids[f"c{i}"] = (Q @ rng.normal(size=3)).astype(np.float32)
    alien = rng.normal(size=d).astype(np.float32)
    alien -= Q @ (Q.T @ alien)                      # fully outside the subspace
    kids["alien"] = alien
    raw = {m: float(i) for i, m in enumerate(sorted(kids))}   # distinct incumbent scores
    raw["alien"] = 100.0                                       # the alien scored hottest
    before = dict(raw)
    organ_res = {"torn": False, "stale": False, "refused": set(),
                 "frames": {"blk": {"Q": Q, "mu": np.zeros(d, dtype=np.float32)}}}
    report = {"blocks_gated": 0, "children_demoted": 0,
              "skipped_by_cause": {"no_key": 0, "stale_isometry": 0, "degenerate": 0,
                                   "torn": 0, "too_small": 0}}
    embed_router._organ_residual_gate("blk", sorted(kids), kids, raw, organ_res, report)
    assert report["children_demoted"] == 1                     # exactly the alien (q90 of 10)
    kept = [m for m in kids if m != "alien"]
    assert all(raw[m] == before[m] for m in kept)              # margins untouched, verbatim
    assert raw["alien"] < min(raw[m] for m in kept)            # demoted below the block


def test_fork_arm_skips_small_blocks_and_counts_the_cause(fork_armed):
    import numpy as np

    from laplace.representation import embed_router
    kids = {f"c{i}": np.ones(8, dtype=np.float32) for i in range(3)}   # < min children
    raw = {m: 1.0 for m in kids}
    organ_res = {"torn": False, "stale": False, "refused": set(),
                 "frames": {"blk": {"Q": np.eye(8, 2, dtype=np.float32), "mu": None}}}
    report = {"blocks_gated": 0, "children_demoted": 0,
              "skipped_by_cause": {"no_key": 0, "stale_isometry": 0, "degenerate": 0,
                                   "torn": 0, "too_small": 0}}
    embed_router._organ_residual_gate("blk", sorted(kids), kids, raw, organ_res, report)
    assert report["skipped_by_cause"]["too_small"] == 1 and report["children_demoted"] == 0


# ---------------------------------------------------------------------------
# C-PRIME (the seal's decisive arm): frames replace the scoring functional
# ---------------------------------------------------------------------------

@pytest.fixture()
def cprime_armed(monkeypatch):
    monkeypatch.setenv("LAPLACE_ORGAN_V1", "1")
    monkeypatch.setenv("LAPLACE_ORGAN_CPRIME", "1")
    monkeypatch.delenv("LAPLACE_ORGAN_RESIDUAL", raising=False)
    monkeypatch.delenv("LAPLACE_BLOCK_RENORM", raising=False)
    from laplace.representation import embed_router
    embed_router._ORGAN_MEMO.clear()
    yield
    embed_router._ORGAN_MEMO.clear()


def test_cprime_serves_report_and_venue(tmp_path: Path, cprime_armed):
    from laplace.representation import embed_router
    from laplace.representation.embed_router import HashBackend
    net = _route_net({"a": 6, "b": 4})
    b = HashBackend()
    (tmp_path / ".meaning_tree.json").write_text("{}")
    _bank_frame_for(tmp_path, net, "a", b)
    rec = embed_router.route(tmp_path, net, "a scattering decay", backend=b)
    assert "+organC" in rec["router"] and "+organR" not in rec["router"]
    cp = rec["organ_cprime"]
    assert cp["blocks_scored"] >= 1 and cp["children_scored"] >= 4
    assert cp["skipped_by_cause"]["no_key"] >= 1


def test_cprime_yields_to_residual_when_both_armed(tmp_path: Path, monkeypatch):
    from laplace.representation import embed_router
    from laplace.representation.embed_router import HashBackend
    monkeypatch.setenv("LAPLACE_ORGAN_V1", "1")
    monkeypatch.setenv("LAPLACE_ORGAN_CPRIME", "1")
    monkeypatch.setenv("LAPLACE_ORGAN_RESIDUAL", "1")
    embed_router._ORGAN_MEMO.clear()
    net = _route_net({"a": 6})
    b = HashBackend()
    (tmp_path / ".meaning_tree.json").write_text("{}")
    _bank_frame_for(tmp_path, net, "a", b)
    rec = embed_router.route(tmp_path, net, "a scattering decay", backend=b)
    assert "organ_cprime" not in rec and "+organC" not in rec["router"]
    assert "organ_residual" in rec              # residual-only, plainly


def test_cprime_scores_in_the_banked_basis(cprime_armed):
    """The functional replacement's unit witness: an in-span child scores near the
    query's own in-span alignment; a child orthogonal to span(Q) scores 0.0 exactly
    (the zero-guard, never a divide)."""
    import numpy as np

    from laplace.representation import embed_router

    d = 16
    rng = np.random.default_rng(9)
    Q, _ = np.linalg.qr(rng.normal(size=(d, 3)).astype(np.float32))
    Q = Q.astype(np.float32)
    inspan = (Q @ np.array([1.0, 0.5, 0.0], dtype=np.float32))
    ortho = rng.normal(size=d).astype(np.float32)
    ortho -= Q @ (Q.T @ ortho)
    vecs = {"in": inspan, "out": ortho}
    raw = {"in": -5.0, "out": -5.0}             # pre-assigned junk the arm must replace
    qraw = (Q @ np.array([1.0, 0.0, 0.0], dtype=np.float32)) + 0.01 * ortho
    organ_cp = {"torn": False, "stale": False, "refused": set(),
                "frames": {"blk": {"Q": Q, "mu": np.zeros(d, dtype=np.float32)}}}
    report = {"blocks_scored": 0, "children_scored": 0,
              "skipped_by_cause": {"no_key": 0, "stale_isometry": 0, "degenerate": 0,
                                   "torn": 0, "too_small": 0}}
    embed_router._organ_cprime_score("blk", ["in", "out"], vecs, raw, qraw,
                                     organ_cp, report)
    assert report["children_scored"] == 2
    assert raw["in"] > 0.85                      # aligned in the banked basis
    assert raw["out"] == 0.0                     # orthogonal projects to zero, guarded


# ---------------------------------------------------------------------------
# B_MATCHED (amendment 6): serve-time basis at C_PRIME's exact coverage
# ---------------------------------------------------------------------------

def test_bmatched_serves_where_the_mask_says_and_never_reads_frame_geometry(tmp_path: Path, monkeypatch):
    from laplace.representation import embed_router
    from laplace.representation.embed_router import HashBackend
    monkeypatch.setenv("LAPLACE_ORGAN_V1", "1")
    monkeypatch.setenv("LAPLACE_ORGAN_BMATCHED", "1")
    monkeypatch.delenv("LAPLACE_ORGAN_CPRIME", raising=False)
    monkeypatch.delenv("LAPLACE_ORGAN_RESIDUAL", raising=False)
    embed_router._ORGAN_MEMO.clear()
    net = _route_net({"a": 6, "b": 4})
    b = HashBackend()
    (tmp_path / ".meaning_tree.json").write_text("{}")
    _bank_frame_for(tmp_path, net, "a", b)          # 'a' carries the mask key; 'b' does not
    rec = embed_router.route(tmp_path, net, "a scattering decay", backend=b)
    assert "+organBM" in rec["router"] and "organ_bmatched" in rec
    bm = rec["organ_bmatched"]
    assert bm["blocks_scored"] >= 1                  # 'a' scored through the serve-time basis
    assert bm["skipped_by_cause"]["no_key"] >= 1     # root/'b' fell through to global cosine
    embed_router._ORGAN_MEMO.clear()


def test_bmatched_matches_incumbent_when_no_mask_exists(tmp_path: Path, monkeypatch):
    """With no frames banked the mask is empty everywhere: B_MATCHED must serve the
    incumbent's exact file lists (coverage zero => arm == A2 by construction)."""
    from laplace.representation import embed_router
    from laplace.representation.embed_router import HashBackend
    net = _route_net({"a": 6, "b": 4})
    b = HashBackend()
    monkeypatch.delenv("LAPLACE_ORGAN_V1", raising=False)
    embed_router._ORGAN_MEMO.clear()
    plain = embed_router.route(tmp_path, net, "a scattering decay", backend=b)
    monkeypatch.setenv("LAPLACE_ORGAN_V1", "1")
    monkeypatch.setenv("LAPLACE_ORGAN_BMATCHED", "1")
    embed_router._ORGAN_MEMO.clear()
    armed = embed_router.route(tmp_path, net, "a scattering decay", backend=b)
    assert [f.get("file") for f in plain["files"]] == [f.get("file") for f in armed["files"]]
    assert armed["organ_bmatched"]["blocks_scored"] == 0
