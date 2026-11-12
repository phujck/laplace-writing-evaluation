"""The register's fold-trace figure selects an EPISODE, not every fast fold.

The figure narrates one regression: a consecutive run of sub-second (empty)
folds, the full rebuild that restored the fold, and the warm incremental after
it. It asserts its own story at generation time, which is why it went red when
the ledger grew: isolated sub-second folds banked weeks later dragged the window
across months and handed the annotation a restore from an unrelated night
("the restored fold no longer lands inside the prior band").

These tests pin the selector: the longest consecutive block of empties is the
episode, and a stray fast fold after it changes nothing.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
REGISTERS = REPO / "site_exports" / "registers"
GEN_PY = REGISTERS / "assets" / "engine" / "generators.py"


@pytest.fixture(scope="module")
def gen():
    if not GEN_PY.exists():                      # the export tree is optional
        pytest.skip("register export tree not present")
    sys.path.insert(0, str(REGISTERS))
    spec = importlib.util.spec_from_file_location("reg_engine_generators", GEN_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def toks():
    sys.path.insert(0, str(REGISTERS))
    import theme                                 # noqa: PLC0415
    return theme.tokens()


@pytest.fixture(autouse=True)
def _restore_timing(gen):
    """The module constant is the ledger path; a test that swaps it puts it back."""
    live = gen.TIMING
    yield
    gen.TIMING = live


def _row(ts: str, s: float, nodes: int) -> str:
    return json.dumps({"ts": ts, "phases": {"meaning_upfold": s}, "nodes": nodes})


def _ledger(rows: list[tuple[str, float, int]], path: Path) -> Path:
    path.write_text("\n".join(_row(*r) for r in rows) + "\n", encoding="utf-8")
    return path


def _fulls() -> list[tuple[str, float, int]]:
    """Nine full folds, spread so the band is 300–600 s."""
    secs = [600.0, 300.0, 550.0, 400.0, 580.0, 350.0, 520.0, 380.0, 320.0]
    return [(f"2026-07-{10 + i:02d}T09:00:00+00:00", s, 17000 + i * 10)
            for i, s in enumerate(secs)]


def _synthetic(extra: list[tuple[str, float, int]]) -> list[tuple[str, float, int]]:
    """The full folds, then the episode (three empties, the restore, the warm
    tail), then whatever the caller banks afterwards."""
    rows = _fulls()
    rows += [("2026-07-24T17:39:00+00:00", 0.31, 23036),
             ("2026-07-24T17:41:00+00:00", 0.26, 23036),
             ("2026-07-24T17:44:00+00:00", 0.27, 23038),
             ("2026-07-28T09:48:00+00:00", 500.0, 19045),      # the restore, in band
             ("2026-07-28T10:11:00+00:00", 14.6, 19056)]       # the warm tail
    return rows + extra


def test_live_ledger_renders(gen, toks):
    """The red this cures: the shipped ledger must draw."""
    svg = gen.fold_trace(toks)
    assert svg.startswith("<svg") and "engine_fold_trace" in svg


def test_stray_fast_fold_after_the_episode_does_not_move_the_window(gen, toks, tmp_path):
    """A single sub-second fold banked weeks later is not a regression."""
    clean = _ledger(_synthetic([]), tmp_path / "clean.jsonl")
    drifted = _ledger(_synthetic([
        ("2026-07-30T13:37:00+00:00", 0.21, 18250),            # one stray fast fold
        ("2026-07-30T13:41:00+00:00", 900.0, 19289),           # an unrelated full fold
        ("2026-07-30T20:05:00+00:00", 33.8, 19302),
    ]), tmp_path / "drifted.jsonl")

    gen.TIMING = clean
    before = gen.fold_trace(toks)
    gen.TIMING = drifted
    after = gen.fold_trace(toks)

    # the window did not stretch: the later rows are reported as the newest run
    # BEYOND the window, never drawn inside it
    assert "latest run since" in after and "2026-07-30" in after
    assert before.count("0.26 s") == after.count("0.26 s") == 1
    assert "500 s" in after and "900 s" not in after
    assert after.count("2026-07-30") == 1           # the caption only


def test_no_episode_refuses(gen, toks, tmp_path):
    """One isolated fast fold is not an episode; the figure refuses to narrate."""
    gen.TIMING = _ledger(
        _fulls()
        + [("2026-07-24T17:39:00+00:00", 0.31, 23036),
           ("2026-07-28T09:48:00+00:00", 355.0, 19045),
           ("2026-07-28T10:11:00+00:00", 14.6, 19056)],
        tmp_path / "single.jsonl")
    with pytest.raises(RuntimeError, match="run of empty folds"):
        gen.fold_trace(toks)
