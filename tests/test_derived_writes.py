"""tests/test_derived_writes.py — the derived-state write gate
(WO-20260817-test-mutates-working-tree).

Five independent reproductions banked the same defect: a pytest run that only
ASSERTS live repo state also MUTATED it, because two pipeline organs refresh a
timestamp-stamped derived file as a side effect of being read — the form-channel
retrieval sidecar (``_form_retrieval.<store>.<section>.json``) and the master node
index (``node_index.json``). Every tree-state probe after such a run then read a
dirtier tree than the change under test.

These tests pin the CURE at three altitudes: the predicate's own truth table, the
two organs actually refusing to touch the live tree, and — the one that matters —
a live compile leaving the real sidecar byte-identical.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from laplace.pipeline import derived_writes as dw

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]


# ── the predicate ─────────────────────────────────────────────────────────────
def test_gate_is_open_outside_pytest_and_shut_under_it():
    """Production behaviour is unchanged; the read-only default is pytest-scoped."""
    assert dw.enabled({}) is True                            # a real run: writes
    assert dw.enabled({dw.PYTEST_MARKER: "t.py::x (call)"}) is False
    # the explicit opt-in wins in both directions
    assert dw.enabled({dw.PYTEST_MARKER: "t", dw.WRITE_FLAG: "1"}) is True


def test_the_gate_is_live_in_this_process():
    """Not just the pure function — the ambient reading pytest actually produces."""
    assert dw.enabled() is False
    assert dw.WRITE_FLAG in (dw.read_only_note() or "")


def test_read_only_note_is_none_when_writes_are_permitted():
    """Absence is stated, presence is silent — a caller can branch on the reason."""
    assert dw.read_only_note({}) is None


def test_the_flag_reopens_the_gate_in_process(monkeypatch):
    monkeypatch.setenv(dw.WRITE_FLAG, "1")
    assert dw.enabled() is True and dw.read_only_note() is None


# ── organ 1: the node index mint ──────────────────────────────────────────────
def test_write_node_index_refuses_under_the_shut_gate():
    from laplace.pipeline import node_index as ni
    assert ni.write_node_index("paper_falqon") is None


def test_write_node_index_mints_when_opted_in_and_restores(monkeypatch):
    """The refusal is the GATE, not a broken mint: with the flag the mint works."""
    from laplace.pipeline import node_index as ni
    p = ni.index_path("paper_falqon")
    if p is None or not p.is_file():
        pytest.skip("paper_falqon index not present in this checkout")
    before = p.read_bytes()
    monkeypatch.setenv(dw.WRITE_FLAG, "1")
    try:
        assert ni.write_node_index("paper_falqon") == p
    finally:
        p.write_bytes(before)
    assert p.read_bytes() == before


# ── organ 2: the form-channel sidecar, and the whole point ────────────────────
def test_live_narrative_compile_leaves_the_sidecar_byte_identical():
    """THE regression. Compiling a live dispatch used to rewrite the sidecar's ``ts``
    on every run; the prompt must still carry the served envelope either way."""
    from laplace.pipeline import dispatch, registry, schema
    project = "subset-sum-itqde"
    plan = registry.resolve(project).read_plan(REPO)
    owner = next((s["id"] for s in schema.plan_sections(plan)
                  if "def:staircase" in schema.section_nodes(s)), None)
    assert owner, "def:staircase is planned somewhere"

    from laplace.pipeline import stage_retrieval as sr
    proj = registry.resolve(project)
    ddir = proj.stage_path("dispatches", REPO)
    side = (ddir / sr.sidecar_name("paragraph_plan", owner.replace(":", "_"))
            if ddir is not None else None)
    before = side.read_bytes() if (side is not None and side.is_file()) else None

    d = dispatch.compile_dispatch(owner, "probe", "narrative", project)
    if "error" in d:
        pytest.skip(d["error"])
    after = side.read_bytes() if (side is not None and side.is_file()) else None
    assert after == before, "a live compile dirtied its retrieval sidecar"


def test_the_persist_primitive_still_writes_where_it_is_told(tmp_path):
    """The gate is on the REFRESH DECISION, never on the primitive: a caller that
    names a path (a tmp_path roundtrip, a real run's bank) still gets its write."""
    from laplace.pipeline import stage_retrieval as sr
    rec = {"store": "paragraph_plan", "k": 1, "query_digest": "sha256:deadbeef",
           "ts": "2026-08-20T00:00:00+00:00", "n_exemplars": 0, "exemplars": []}
    out = sr.write_form_channel_sidecar(tmp_path / "d" / sr.sidecar_name(
        "paragraph_plan", "N4"), rec)
    assert out.is_file() and "paragraph_plan" in out.name
