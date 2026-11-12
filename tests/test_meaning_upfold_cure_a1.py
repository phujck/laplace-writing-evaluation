"""CURE-A1: cluster-local GPU eigensolver recovery and typed exhaustion."""
from types import SimpleNamespace

import numpy as np
import pytest

from laplace.representation import device_policy, spectral_gpu
from laplace.pipeline import dial_profiles as dials
from laplace.engine import meaning_upfold as mu


@pytest.fixture(autouse=True)
def _dial_store(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_DIALS_ROOT", str(tmp_path))
    dials.pour_genesis(tmp_path)


def _fake_gpu_fold(monkeypatch):
    fs = object.__new__(spectral_gpu.FoldSpectral)
    fs.backend = "gpu"
    fs.n = 12
    fs.xp = SimpleNamespace(float64="float64")
    return fs


def test_nonconvergence_retries_precision_jitter_then_power(monkeypatch):
    fs = _fake_gpu_fold(monkeypatch)
    calls = []

    def eigsh(k, **kwargs):
        calls.append(("lanczos", k, kwargs))
        raise np.linalg.LinAlgError("Eigenvalues did not converge")

    def power(k, **kwargs):
        calls.append(("power", k, kwargs))
        return "embedding", "eigenvalues"

    monkeypatch.setattr(fs, "_embedding_eigsh", eigsh)
    monkeypatch.setattr(fs, "_embedding_power", power)
    assert fs.embedding(3) == ("embedding", "eigenvalues")
    assert calls == [
        ("lanczos", 3, {}),
        ("lanczos", 3, {"dtype": "float64", "tol": 1e-5}),
        ("lanczos", 3, {"dtype": "float64", "jitter": 1e-8, "tol": 1e-5}),
        ("power", 3, {"tol": 1e-5, "iterations": 256}),
    ]


def test_all_retries_raise_typed_eigensolver_decline(monkeypatch):
    fs = _fake_gpu_fold(monkeypatch)
    failure = np.linalg.LinAlgError("Eigenvalues did not converge")
    monkeypatch.setattr(fs, "_embedding_eigsh", lambda *a, **k: (_ for _ in ()).throw(failure))
    monkeypatch.setattr(fs, "_embedding_power", lambda *a, **k: (_ for _ in ()).throw(failure))
    with pytest.raises(spectral_gpu.EigensolverDeclined) as caught:
        fs.embedding(3)
    assert [attempt["stage"] for attempt in caught.value.attempts] == [
        "float32-lanczos", "float64-lanczos", "float64-jittered-lanczos",
        "float64-block-power",
    ]


def test_non_finite_eigenpairs_enter_the_retry_law(monkeypatch):
    fs = _fake_gpu_fold(monkeypatch)
    fs.xp = SimpleNamespace(asnumpy=np.asarray)
    with pytest.raises(np.linalg.LinAlgError, match="finite") as caught:
        fs._finish_embedding(np.asarray([1.0, np.nan]), np.ones((3, 2)), np.ones(3))
    assert fs._nonconvergence(caught.value)


def test_declined_cluster_is_fingerprinted_and_next_cluster_still_splits(monkeypatch):
    members1 = [f"a{i}" for i in range(11)]
    members2 = [f"b{i}" for i in range(11)]
    members = members1 + members2
    clusters = {
        "c1": {"members": list(members1), "label": "one", "sealed": False},
        "c2": {"members": list(members2), "label": "two", "sealed": False},
    }
    parents = {"c1": "", "c2": "", **{m: "c1" for m in members1},
               **{m: "c2" for m in members2}}
    row = {member: i for i, member in enumerate(members)}
    X = np.asarray([[1.0, i / 100.0] for i in range(len(members))])
    leaf_sha = {member: f"sha-{member}" for member in members}
    attempts = [{"stage": "float64-block-power", "error": "LinAlgError: did not converge"}]
    calls = []

    def split(block, level=1):
        calls.append(len(block))
        if len(calls) == 1:
            raise spectral_gpu.EigensolverDeclined(attempts)
        return 2, np.asarray([0] * 6 + [1] * 5)

    monkeypatch.setattr(mu, "_best_split", split)
    monkeypatch.setattr(mu, "_gpu_fold", {"choice": ("gpu", ""), "announced": True})
    minted = []
    mu._resplit_into("c1", members1, 1, clusters, parents, X, row, minted, leaf_sha)
    mu._resplit_into("c2", members2, 1, clusters, parents, X, row, minted, leaf_sha)

    decline = clusters["c1"]["split_decline"]
    assert decline["type"] == "cut_decline"
    assert decline["reason"] == "eigensolver-declined"
    assert decline["members_sha256"] == mu._member_fingerprint(members1, leaf_sha)
    assert calls == [11, 11]
    assert minted and mu._gpu_fold["choice"][0] == "gpu"


def test_full_fold_completes_with_a_fingerprinted_declined_cluster(tmp_path, monkeypatch):
    from laplace.representation import embed_router
    names = [f"leaf/{i:02d}.md" for i in range(20)]
    residue = {name: {"essence": name, "keywords": ["fixture"], "sealed": False}
               for name in names}
    backend = SimpleNamespace(name="fixture-a1")
    X = np.asarray([[1.0, i / 100.0] for i in range(len(names))])
    attempts = [{"stage": "float64-block-power", "error": "LinAlgError: did not converge"}]
    monkeypatch.setattr(embed_router, "get_backend", lambda: backend)
    monkeypatch.setattr(mu, "_embed", lambda *a, **k: X)
    monkeypatch.setattr(mu, "_best_split",
                        lambda *a, **k: (_ for _ in ()).throw(
                            spectral_gpu.EigensolverDeclined(attempts)))

    parent_map, cluster_nodes = mu._cluster_residue_body(tmp_path, residue, "")
    assert len(cluster_nodes) == 1 and set(parent_map) == set(names) | set(cluster_nodes)
    decline = next(iter(cluster_nodes.values()))["split_decline"]
    assert decline["type"] == "cut_decline"
    assert decline["reason"] == "eigensolver-declined"
    assert decline["members_sha256"].startswith("sha256:")


def test_unexpected_gpu_fault_refuses_without_changing_fold_wide_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(mu, "_gpu_fold", {"choice": ("gpu", ""), "announced": True})
    monkeypatch.setattr(mu, "_fold_backend", lambda: ("gpu", ""))
    monkeypatch.setattr(mu, "_best_split_gpu",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("device fault")))
    monkeypatch.setattr(mu, "_best_split_dense", lambda *a, **k: pytest.fail("CPU split ran"))
    monkeypatch.setenv(device_policy.LOG_OVERRIDE, str(tmp_path / "fallback.jsonl"))
    monkeypatch.setenv(device_policy.REQUIRE_FLAG, "1")
    with pytest.raises(device_policy.DeviceRequired, match="LAPLACE_REQUIRE_GPU"):
        try:
            mu._best_split([[1.0, 0.0], [0.0, 1.0]])
        except Exception:
            pytest.fail("the additive fold boundary swallowed a device refusal")
    assert mu._gpu_fold["choice"] == ("gpu", "")
