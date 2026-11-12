"""Tests for hello_generator - the hello reconstructed by a Haiku swarm.

These pin the PURE halves (the engine pattern: script prepares + composes, the orchestrator spawns
the swarm): prepare shatters the reconstructed self into per-dimension slice files + a small
manifest; compose assembles the swarm's fragments into the five-point briefing. The swarm itself
(the Haiku fan-out) is the orchestrator's, not unit-tested here.
"""

from __future__ import annotations

from pathlib import Path

from laplace.engine.hello_generator import compose, prepare

REPO = Path(__file__).resolve().parents[1]


def test_prepare_shatters_the_self_into_a_small_manifest(tmp_path):
    """prepare reconstructs the live self and writes one slice file per orientation dimension;
    the manifest carries pointers + asks (no payloads), so the swarm's args stay small."""
    manifest = prepare(REPO, cache_dir=tmp_path)
    assert manifest, "prepare produced no briefs from the live engine state"
    dims = {row["dimension"] for row in manifest}
    assert "where_and_next" in dims, "the where-we-are/next-move slice was not prepared"
    assert "blocked_on_author" in dims, "the live author-forks did not fan out into briefs"
    for row in manifest:
        assert set(row) == {"dimension", "path", "ask"}, "manifest rows must be pure pointers"
        p = Path(row["path"])
        assert p.exists() and p.read_text(encoding="utf-8").strip(), "a slice file is missing or empty"


def test_compose_assembles_the_five_points():
    """compose folds the swarm's fragments into the briefing shape - deterministic structure."""
    fragments = [
        {"dimension": "where_and_next", "text": "On the ingestion main track; next move is Gate 2."},
        {"dimension": "since_last_close", "text": "Built the self_corpus organ; 254 tests green."},
        {"dimension": "blocked_on_author", "text": "Decide the kind taxonomy."},
        {"dimension": "blocked_on_author", "text": "Settle raw-data persistence (F11)."},
    ]
    out = compose(fragments)
    assert "Where we are / the next move." in out
    assert "Since last close." in out
    assert "Blocked on you:" in out
    assert "- Decide the kind taxonomy." in out and "- Settle raw-data persistence (F11)." in out
    assert "How to close." in out


def test_compose_is_defensive_on_no_fragments():
    """An empty swarm still yields the fixed scaffold (live probe + how-to-close), never a crash."""
    out = compose([])
    assert "Live probe" in out and "How to close." in out


def test_prepare_is_defensive_on_an_engine_less_tree(tmp_path):
    """No engine files -> no briefs, never an error (the generator is a convenience, not a hard dep)."""
    empty = tmp_path / "repo"
    empty.mkdir()
    assert prepare(empty, cache_dir=tmp_path / "cache") == []
