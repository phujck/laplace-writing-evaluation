"""The metric distillation, pinned: the wire becomes geometry (weights-from-concepts), the
identity anchor keeps the bend earned, and the report carries a readable spectrum.

Synthetic wire: two vocabulary islands (alpha-texts, beta-texts) wired ACROSS the islands -
under the raw metric a wired pair looks far (different vocabularies), so the identity AUC is
poor and training must lift it. That is the distillation's whole job in miniature.
"""

from __future__ import annotations

import json

import pytest

from laplace.representation import metric_distill
from laplace.representation.embed_router import HashBackend

np = pytest.importorskip("numpy")


_X_WORDS = ["quark", "lattice", "spinor", "tensor", "gauge", "photon",
            "boson", "fermion", "brane", "dilaton", "axion", "gluon"]
_Y_WORDS = ["ledger", "invoice", "market", "tariff", "equity", "bond",
            "escrow", "margin", "audit", "broker", "hedge", "yield"]


def _island_vecs(n: int = 12):
    """Each node gets its OWN vocabulary plus an island-common term - within-island similarity
    is moderate (not collapsed to a point), across-island similarity is ~zero, and the wire runs
    ACROSS the islands, so only training can make wired pairs near."""
    b = HashBackend()
    ids, texts = [], []
    for i in range(n):
        ids += [f"x{i}", f"y{i}"]
        texts += [f"alpha {_X_WORDS[i]} {_X_WORDS[(i + 1) % n]} field",
                  f"beta {_Y_WORDS[i]} {_Y_WORDS[(i + 1) % n]} account"]
    vecs = dict(zip(ids, b.embed(texts), strict=True))
    pairs = [(f"x{i}", f"y{i}") for i in range(n)]
    return vecs, pairs


def test_training_lifts_the_wire():
    vecs, pairs = _island_vecs()
    rep = metric_distill.train(vecs, pairs, epochs=12, anchor=0.01)
    assert rep["auc_trained"] > rep["auc_identity"]       # the wire is genuinely learned
    M = rep["M"]
    assert np.allclose(M, M.T, atol=1e-5)                 # the similarity stays symmetric
    assert rep["drift"] > 0                               # the space moved...
    assert rep["spectrum"]["top"][0] < 50                 # ...but not unboundedly (anchor held)


def test_same_seed_same_metric():
    vecs, pairs = _island_vecs()
    a = metric_distill.train(vecs, pairs, epochs=3)
    b = metric_distill.train(vecs, pairs, epochs=3)
    assert a["auc_trained"] == b["auc_trained"]
    assert np.allclose(a["M"], b["M"])


def test_too_little_wire_refuses():
    vecs, _ = _island_vecs(4)
    with pytest.raises(ValueError):
        metric_distill.train(vecs, [("x0", "y0")])


# ---------------------------------------------------------------------------
# THE REFUSAL GUARD, IN THE CALLEE (WO-20260817-metric-guard-into-callee +
# WO-20260817-restored-metric-honest-mtime, the thin-systems audit 2026-08-17)
# ---------------------------------------------------------------------------
#
# main() ships M with np.savez BEFORE the hello gate runs. On a refusal it used to unlink
# unconditionally - deleting whatever GOOD standing M was already there (the 2026-07-15 loss).
# The guard lived at ONE of three call sites (scripts/reembed.py); it now lives here, so every
# producer inherits it, and the restore preserves the prior artifact's ORIGINAL mtime because
# three standing staleness guards read that mtime to decide STALE.

class _StubBackend:
    name = "stub"


def _stub_main_deps(monkeypatch, *, gate_passes: bool):
    """Stub computation; each CLI call selects its whole disposable repository."""
    from laplace.engine import conceptric
    from laplace.representation import embed_router
    monkeypatch.setattr(embed_router, "get_backend", lambda: _StubBackend())
    monkeypatch.setattr(conceptric, "load_network", lambda root: {"nodes": {}})
    monkeypatch.setattr(embed_router, "ensure_embeddings",
                        lambda root, net, backend, bulk=False: {"vectors": {}})
    monkeypatch.setattr(metric_distill, "wire_pairs", lambda root, net: [("a", "b")])
    monkeypatch.setattr(metric_distill, "train", lambda vecs, pairs, **kw: {
        "evaluation": {"ids": ["a", "b", "c"], "pairs": [["a", "b"]], "X": np.eye(4, dtype="float32"), "table": np.array([[0, 1, 2]], dtype="int32")},
        "device": "gpu", "n_train": 1, "M": np.eye(4), "auc_identity": 0.5, "auc_trained": 0.9, "n_pos": 1, "n_neg": 4})
    monkeypatch.setattr(metric_distill, "hello_gate",
                        lambda root, net, metric=None: {"found": 5 if gate_passes else 1, "total": 5,
                                           "pass": gate_passes})


def test_refusal_restores_the_prior_metric_bytes_and_mtime(tmp_path, monkeypatch, capsys):
    metric_path = tmp_path / ".metric_M.npz"
    metric_path.write_bytes(b"PRIOR-GOOD-M")
    prior = metric_path.read_bytes()
    old = 1_600_000_000
    import os
    os.utime(metric_path, (old, old))

    _stub_main_deps(monkeypatch, gate_passes=False)
    rc = metric_distill.main(["--repo", str(tmp_path), "--full-metric"])

    assert rc == 1                                   # a refusal is still a refusal
    assert metric_path.is_file(), "the decline must not delete a good standing M"
    assert metric_path.read_bytes() == prior         # ...and must restore it byte-for-byte
    # THE MTIME: a restore stamped 'now' would forge freshness the restored M does not have,
    # and the three mtime staleness guards would read it as current.
    assert int(metric_path.stat().st_mtime) == old
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["shipped"] is False
    assert verdict["restored_prior_artifact"] is True


def test_refusal_with_nothing_standing_leaves_nothing(tmp_path, monkeypatch, capsys):
    metric_path = tmp_path / ".metric_M.npz"
    _stub_main_deps(monkeypatch, gate_passes=False)

    assert metric_distill.main(["--repo", str(tmp_path), "--full-metric"]) == 1
    assert not metric_path.exists()                  # nothing was standing; nothing is restored
    assert json.loads(capsys.readouterr().out)["restored_prior_artifact"] is False


def test_a_passing_gate_still_ships_the_new_metric(tmp_path, monkeypatch, capsys):
    metric_path = tmp_path / ".metric_M.npz"
    metric_path.write_bytes(b"PRIOR-GOOD-M")
    _stub_main_deps(monkeypatch, gate_passes=True)

    assert metric_distill.main(["--repo", str(tmp_path), "--full-metric"]) == 0
    assert metric_path.read_bytes() != b"PRIOR-GOOD-M", "a passing gate ships the NEW M"
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["shipped"] is True
    assert "restored_prior_artifact" not in verdict


def test_cli_repo_keeps_metric_receipt_and_pairs_together(tmp_path, monkeypatch, capsys):
    selected = tmp_path / "selected"
    default = tmp_path / "default"
    selected.mkdir()
    default.mkdir()
    # A forgotten --repo must hit this disposable root, never the real source checkout.
    monkeypatch.setattr(metric_distill, "__file__", str(default / "src/laplace/representation/metric_distill.py"))
    names = (".metric_M.npz", ".metric_M.receipt.json", ".metric_pairs.json")
    prior = {}
    for name in names:
        path = default / name
        path.write_bytes(b"unselected repository state")
        prior[name] = (path.read_bytes(), path.stat().st_mtime_ns)
    _stub_main_deps(monkeypatch, gate_passes=True)

    assert metric_distill.main(["--repo", str(selected), "--full-metric"]) == 0
    assert json.loads(capsys.readouterr().out)["shipped"] is True
    assert all((selected / name).is_file() for name in names)
    pairs = json.loads((selected / ".metric_pairs.json").read_text())
    assert pairs["evaluation_ids"] == ["a", "b", "c"]
    for name in names:
        path = default / name
        assert (path.read_bytes(), path.stat().st_mtime_ns) == prior[name]


@pytest.mark.parametrize("reached,missing,expected", [(True, False, True), (False, False, False), (True, True, False)])
def test_standing_gate_follows_only_retrieved_handle_and_verifies_sources(tmp_path, monkeypatch, reached, missing, expected):
    from laplace.engine import conceptric
    (tmp_path / "HANDOFF.md").write_text("current work")
    if not missing:
        (tmp_path / "EIGEN_PROTOCOL.md").write_text("current operating sequence")
    members = ["HANDOFF.md", "EIGEN_PROTOCOL.md"]
    net = {"nodes": {conceptric.STANDING: {"members": members}}}
    monkeypatch.setattr(conceptric, "fire_by_grade", lambda *a, **kw: {
        "hits": [{"recovered": conceptric.STANDING if reached else "HANDOFF.md"}],
        "per_grade": {}, "router": "fixture"})
    monkeypatch.setattr(conceptric, "expand", lambda *a: {"members": [{"id": name} for name in members]})
    out = metric_distill.hello_gate(tmp_path, net)
    assert out["pass"] is expected
    assert out["found"] == (2 if expected else 1)
    assert out["source_hashes"]["HANDOFF.md"].startswith("sha256:")
