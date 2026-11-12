"""The selection-identity fixture (migration gate 3 of
RUL-20260820-selection-criterion-derived, built 2026-08-23 the accounting day).

A planted three-cluster corpus with a known right answer: both selectors must
find it, the residual selector must be deterministic (same X -> same pick, same
labels), and the declared chi ladder must serve per level. The fixture pins the
swap's identity - a selector change that moves THIS pick is a regression, not a
migration."""
from __future__ import annotations

import os

import numpy as np
import pytest

from laplace.engine import meaning_upfold as mu


@pytest.fixture()
def planted_corpus():
    rng = np.random.default_rng(7)
    centers = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
    X = np.vstack([c + 0.05 * rng.standard_normal((40, 3)) for c in centers])
    X = np.pad(X, ((0, 0), (0, 29)))
    X += 0.01 * rng.standard_normal(X.shape)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    return X


@pytest.fixture(autouse=True)
def _dense_path(monkeypatch):
    # the fixture pins the CPU dense path: the identity being tested is the
    # SELECTOR's, not the eigensolver's (that parity has its own gate).
    monkeypatch.setenv("LAPLACE_FOLD_GPU_MIN_N", "999999")


def test_both_selectors_find_the_planted_k(planted_corpus, monkeypatch):
    monkeypatch.delenv("LAPLACE_SELECTOR", raising=False)
    k_sil, _ = mu._best_split(planted_corpus, level=1)
    monkeypatch.setenv("LAPLACE_SELECTOR", "residual")
    k_res, _ = mu._best_split(planted_corpus, level=1)
    assert k_sil == 3, f"silhouette lost the planted k: {k_sil}"
    assert k_res == 3, f"the residual selector lost the planted k: {k_res}"


def test_residual_selector_is_deterministic(planted_corpus, monkeypatch):
    monkeypatch.setenv("LAPLACE_SELECTOR", "residual")
    k1, l1 = mu._best_split(planted_corpus, level=1)
    k2, l2 = mu._best_split(planted_corpus, level=1)
    assert k1 == k2
    assert (np.asarray(l1) == np.asarray(l2)).all()


def test_chi_ladder_is_the_measured_declaration():
    # AMEND-20260823-chi-ladder-declared: level 1 -> 16, deeper -> 8. Derived
    # from the trilogy (SELECTOR_BENCH + CHI_DECLARATION_BENCH + CHI_LEVEL3);
    # depth-INdependence was refuted by measurement, so a flat chi here is a
    # regression against the banked evidence.
    assert mu._selector_chi(1) == 16
    assert mu._selector_chi(2) == 8
    assert mu._selector_chi(5) == 8
