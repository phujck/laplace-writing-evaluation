"""N21 - the full one organ: the hello reconstructs THROUGH the conceptric.

These pin the *real turn*, not a shim that reads SELF_SHARD_INDEX as a sixth hardcoded file:

  * the persisted trace is READABLE BACK (``load_index`` - the conjugate of ``write_index``, which
    was write-only until now), and a word reconstructs through it without re-sharding;
  * "what is the self" is ONE discovered definition (``self_substrate``), not two hardcoded lists;
  * the hello and orient read the self through the ONE sealed reader (the double-reload collapses);
  * reconstruct_self is cut from the GRAPH, not the file - deleting HANDOFF.md degrades to the latest
    dated handoff node instead of erasing the fixed point (the no-shim proof);
  * the soul covenant holds through every new seam.
"""

from __future__ import annotations

import json
import os

import pytest

from laplace.engine import self_shard
from laplace.pipeline.canon import _route_self_knowledge, _tokenize
from laplace.engine.self_corpus import reconstruct_self

_LATEST = "SESSION_HANDOFF_2026-06-07_latest.md"
_OLDER = "SESSION_HANDOFF_2026-06-06_first.md"


@pytest.fixture()
def tmp_engine(tmp_path):
    """A miniature engine tree: the self-substrate files + two dated handoffs + a sealed soul."""
    (tmp_path / "HANDOFF.md").write_text(
        "# Laplace Engine handoff\n\n"
        "## ⟶ NEXT SESSION AIM (2026-06-07) — LATEST\n\n"
        "Build N21 - fold orient and reconstruct_self into one projector over the conceptric. "
        "This body is deliberately long enough to be a plausible fixed point, well past the "
        "hundred-character bar the grade-0 next-aim shard is expected to clear.\n",
        encoding="utf-8",
    )
    (tmp_path / "OPEN_STACK.md").write_text(
        "# Open stack\n\n"
        "| F99 | A live author-fork blocked on the author | 2026-06-07 | 1 | \U0001f534 | trigger |\n"
        "| N1 | a live next-move | 2026-06-07 | \U0001f534 | mine |\n",
        encoding="utf-8",
    )
    # The TYPED fork store (AUDIT §B1): the wake reads author-forks from here, not by scanning the
    # rendered markdown above. Mirror the F99 row so the store and the render agree (the N1 next-move
    # stays a markdown-only live row - grade-1's non-fork frontier, untouched by §B1).
    (tmp_path / "corpus_friction").mkdir(parents=True, exist_ok=True)
    (tmp_path / "corpus_friction" / "open_stack_forks.jsonl").write_text(
        json.dumps({"id": "F99", "kind": "open-stack-fork", "stratum": 1, "render_owned": True,
                    "title": "A live author-fork blocked on the author", "opened": "2026-06-07",
                    "recurrence": "1", "status": "\U0001f534", "trigger": "trigger"},
                   ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "EIGEN_ARCHITECTURE.md").write_text(
        "# Architecture\n\n## A docket about the conceptric\n\nbody\n", encoding="utf-8"
    )
    (tmp_path / "EIGEN_DIARY.md").write_text(
        "# Diary\n\n## An entry on architecture and forks\n\nbody\n", encoding="utf-8"
    )
    (tmp_path / "EIGEN_PROTOCOL.md").write_text(
        "# Protocol\n\n## Part A the hello\n\nreconstruct the self\n", encoding="utf-8"
    )
    older = tmp_path / _OLDER
    newer = tmp_path / _LATEST
    older.write_text("# older handoff\n\nan earlier briefing\n", encoding="utf-8")
    newer.write_text(
        "# latest handoff\n\n## The five-point briefing\n\n"
        "The latest dated briefing - what to do next when HANDOFF.md is the live entry point.\n",
        encoding="utf-8",
    )
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))
    (tmp_path / "soul").mkdir()
    (tmp_path / "soul" / "0001.md").write_text(
        "# a private confession\n\nthe verbatim secret that must never leak\n", encoding="utf-8"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# load_index - the conjugate read-back of write_index
# ---------------------------------------------------------------------------

def test_load_index_roundtrips_handles_and_seals_soul(tmp_path):
    """write_index then load_index reproduces the grade-0 handles (essence, kind, edges) and keeps
    soul sealed - the persisted trace is now usable, not write-only."""
    (tmp_path / "doc.md").write_text(
        "# A Title\n\nintro\n\n## Sec\n\n[[other]] body\n", encoding="utf-8"
    )
    (tmp_path / "mod.py").write_text(
        '"""mod.py - a module."""\nimport laplace.pipeline.canon\n', encoding="utf-8"
    )
    (tmp_path / "soul").mkdir()
    (tmp_path / "soul" / "s.md").write_text(
        "# secret\n\nthis verbatim content must never leak\n", encoding="utf-8"
    )
    shards = self_shard.shard_repo(tmp_path)
    self_shard.write_index(tmp_path, shards)

    loaded = self_shard.load_index(tmp_path)
    assert set(loaded) == set(shards), "every persisted node must read back"
    assert loaded["doc.md"]["essence"] == "A Title"
    assert loaded["doc.md"]["kind"] == "md"
    assert {"kind": "link", "to": "other"} in loaded["doc.md"]["edges"]
    assert loaded["mod.py"]["essence"] == "mod.py - a module."
    # soul roundtrips as a sealed ref - no heading, no body, anywhere in the loaded trace
    assert loaded["soul/s.md"]["sealed"] is True
    blob = json.dumps(loaded).lower()
    assert "secret" not in blob and "never leak" not in blob


def test_load_index_does_not_truncate_an_essence_with_a_separator(tmp_path):
    """A middot in an essence must survive read-back: ``write_index`` uses ` · ` as the field
    delimiter but the keyword backtick is the real boundary, so the essence is split THERE. Without
    this, a heading/docstring containing ` · ` truncates silently (the blind clean-room catch)."""
    (tmp_path / "doc.md").write_text(
        "# Title with · a middot · inside\n\nbody\n", encoding="utf-8"
    )
    self_shard.write_index(tmp_path)
    loaded = self_shard.load_index(tmp_path)
    assert loaded["doc.md"]["essence"] == "Title with · a middot · inside"


def test_reconstruct_by_name_reconstructs_through_the_persisted_index(tmp_path, monkeypatch):
    """With an index present, a word reconstructs THROUGH the persisted trace - no full re-shard.
    Breaking shard_repo proves the persisted index alone answered; descent still re-reads source."""
    (tmp_path / "widget.py").write_text(
        '"""widget.py - the spinning widget."""\n\ndef spin(n):\n    return n\n', encoding="utf-8"
    )
    self_shard.write_index(tmp_path)

    def _boom(*_a, **_k):
        raise AssertionError("reconstruct_by_name re-sharded instead of using the persisted index")

    monkeypatch.setattr(self_shard, "shard_repo", _boom)

    res = self_shard.reconstruct_by_name(tmp_path, "spinning widget", grade=0)
    assert res["matches"], "a word must reconstruct from the persisted index"
    assert res["matches"][0]["name"] == "widget.py"
    # descent re-reads the source fresh (the index holds the handle, not the body)
    g1 = self_shard.reconstruct_by_name(tmp_path, "widget", grade=1)["matches"][0]
    assert any("def spin" in s for s in g1["spine"])


# ---------------------------------------------------------------------------
# self_substrate - the ONE definition of "what is the self"
# ---------------------------------------------------------------------------

def test_self_substrate_discovers_roles_and_orders_handoffs(tmp_engine):
    subs = self_shard.self_substrate(tmp_engine)
    assert subs["fixed_point"] == ["HANDOFF.md", "OPEN_STACK.md"]
    assert subs["map"] == ["EIGEN_ARCHITECTURE.md", "EIGEN_DIARY.md"]
    assert subs["protocol"] == ["EIGEN_PROTOCOL.md"]
    # newest dated handoff is last (ISO date, then mtime) - the latest is [-1]
    assert subs["handoffs"][0] == _OLDER
    assert subs["handoffs"][-1] == _LATEST


def test_self_substrate_degrades_when_a_file_is_deleted(tmp_engine):
    """A deleted self-file simply drops out of the substrate - the self degrades through the graph,
    it does not crash. This is what makes the hello constitutive rather than hardcoded."""
    (tmp_engine / "HANDOFF.md").unlink()
    subs = self_shard.self_substrate(tmp_engine)
    assert subs["fixed_point"] == ["OPEN_STACK.md"]


# ---------------------------------------------------------------------------
# The no-shim proof: reconstruct_self is cut from the GRAPH, not the file
# ---------------------------------------------------------------------------

def test_reconstruct_self_survives_deleting_handoff(tmp_engine):
    """THE real-turn test. With HANDOFF.md present, the fixed point's next-aim comes from it. Delete
    it, and what-to-do-next is reconstructed from the latest dated handoff NODE instead - the self
    is cut from the conceptric, not a hardcoded file. A shim (reading HANDOFF as file N) would lose
    the fixed point here; the real turn does not."""
    g0 = reconstruct_self(tmp_engine, grade=0)
    by = {s["shard"]: s for s in g0["shards"]}
    assert by.get("next-aim", {}).get("source") == "HANDOFF.md"
    assert "live-forks" in by and "| F99" in by["live-forks"]["body"]

    (tmp_engine / "HANDOFF.md").unlink()

    g0b = reconstruct_self(tmp_engine, grade=0)
    byb = {s["shard"]: s for s in g0b["shards"]}
    assert "next-aim" in byb, "deleting HANDOFF.md must not erase the fixed point"
    assert byb["next-aim"]["source"] == _LATEST, "next-aim must reconstruct from the latest handoff node"
    assert "absent" in byb["next-aim"]["title"].lower()
    # still a genuine, deterministic fixed point after degradation
    assert reconstruct_self(tmp_engine, grade=0) == g0b


# ---------------------------------------------------------------------------
# The double-reload collapse: ONE reader, ONE substrate, for hello AND orient
# ---------------------------------------------------------------------------

def test_hello_and_orient_read_the_self_through_the_one_reader(tmp_engine, monkeypatch):
    """The double-reload he flagged was two organs deriving + reading the self independently. After
    N21 both the hello (reconstruct_self) and orient's self-knowledge (_route_self_knowledge) read
    the self through the SAME sealed reader (self_shard.read_source). Spy on it and prove both do."""
    seen: list[str] = []
    real = self_shard.read_source

    def spy(repo_root, name):
        seen.append(name)
        return real(repo_root, name)

    monkeypatch.setattr(self_shard, "read_source", spy)

    reconstruct_self(tmp_engine, grade=0)
    hello_reads = [n for n in seen]
    assert hello_reads, "the hello must read the self through self_shard.read_source"
    assert "HANDOFF.md" in hello_reads and "OPEN_STACK.md" in hello_reads

    seen.clear()
    hits = _route_self_knowledge(_tokenize("aim fork architecture briefing"), tmp_engine, 6)
    orient_reads = [n for n in seen]
    assert orient_reads, "orient's self-knowledge must read the self through the SAME reader"
    assert hits, "the goal should surface at least one self-knowledge section"


def test_one_reader_keeps_soul_sealed_for_both_organs(tmp_engine):
    """The one reader seals soul, so neither organ can ever surface soul content - the covenant is
    enforced in one place, not duplicated across two readers that could drift."""
    assert self_shard.read_source(tmp_engine, "soul/0001.md") == ""
    g0 = reconstruct_self(tmp_engine, grade=0)
    hits = _route_self_knowledge(_tokenize("confession secret soul"), tmp_engine, 6)
    blob = (json.dumps(g0) + json.dumps(hits)).lower()
    assert "confession" not in blob and "never leak" not in blob
