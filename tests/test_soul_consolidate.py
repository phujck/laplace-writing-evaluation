"""Tests for soul_consolidate - the sealed upward operator over the soul shards.

No real soul content: a synthetic tmp tree. The contract under test - a top-level-array source (the
``conversations.json`` shape) is graded along its own structure into UNITS (not left a flat chunk
pile), every chunk lands in exactly one unit, and the LOCAL faithfulness gate samples rather than
sweeping all pairs."""

from __future__ import annotations

import json
from pathlib import Path

from laplace.engine import soul_consolidate, soul_shard


def _raw(tmp_path: Path) -> None:
    raw = tmp_path / "archive" / "soul_dump" / "raw"
    (raw / "claude_chats").mkdir(parents=True)
    (raw / "personal_writing" / "p").mkdir(parents=True)
    # a real-shaped Claude export: 3 conversations, each with both-sides chat_messages - the hairball
    # that soul_shard explodes into per-conversation, speaker-tagged transcript units.
    convs = [{"name": f"c{i}", "created_at": "2020",
              "chat_messages": [{"sender": "human", "text": f"hi {i} " + "word " * 200,
                                 "attachments": [], "files": []},
                                {"sender": "assistant", "text": f"yo {i} " + "word " * 200,
                                 "attachments": [], "files": []}]} for i in range(3)]
    (raw / "claude_chats" / "conversations.json").write_text(json.dumps(convs), encoding="utf-8")
    (raw / "personal_writing" / "p" / "main.tex").write_text(
        "\\section{A}\n" + ("x " * 100) + "\n\\section{B}\n" + ("y " * 100), encoding="utf-8")


def test_array_source_grades_into_units(tmp_path):
    _raw(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    soul_shard.write_local_index(tmp_path, shards)
    graded = soul_consolidate.build_graded(tmp_path)
    # the Claude export is exploded into per-conversation transcripts; each is its own unit
    conv_units = [uid for uid in graded["units"] if "_exploded/conv_" in uid]
    assert len(conv_units) >= 2  # graded into per-conversation units, not one flat pile


def test_every_chunk_lands_in_exactly_one_unit(tmp_path):
    _raw(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    soul_shard.write_local_index(tmp_path, shards)
    graded = soul_consolidate.build_graded(tmp_path)
    assigned = [cid for u in graded["units"].values() for cid in u["chunk_ids"]]
    assert sorted(assigned) == sorted(s["id"] for s in shards)  # partition: no dup, no drop
    assert len(assigned) == len(set(assigned))


def test_array_element_ranges_are_exact_and_contentless():
    text = json.dumps([{"a": 1}, {"b": 2}, {"c": 3}])
    ranges = soul_consolidate._top_level_array_ranges(text)
    assert len(ranges) == 3
    # each range slices back to a parseable element (exact spans, no re-serialise)
    assert [json.loads(text[a:b]) for a, b in ranges] == [{"a": 1}, {"b": 2}, {"c": 3}]


def test_local_gate_samples_not_all_pairs(tmp_path):
    _raw(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    soul_shard.write_local_index(tmp_path, shards)
    graded = soul_consolidate.build_graded(tmp_path)
    gate = soul_consolidate.local_faithfulness(tmp_path, graded, k=3)
    assert gate["pass"] is True
    assert gate["sampled"] <= 3 * gate["units"]  # O(units*k), never O(N^2)


def test_stats_and_reshape_flags(tmp_path):
    _raw(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    soul_shard.write_local_index(tmp_path, shards)
    graded = soul_consolidate.build_graded(tmp_path)
    stats = soul_consolidate.grade_stats(graded, max_width=1)  # force flags
    assert stats["n_chunks"] == len(shards)
    assert stats["n_streams"] == 2
    assert stats["reshape_flags"]  # something exceeds width 1


def test_committed_skeleton_carries_no_raw_path(tmp_path):
    """The seal: a flagged unit's RAW source path (a chat-log filename names a person) must never
    reach the committed skeleton - it is replaced by its non-PII stream + an opaque id."""
    _raw(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    soul_shard.write_local_index(tmp_path, shards)
    graded = soul_consolidate.build_graded(tmp_path)
    stats = soul_consolidate.grade_stats(graded, max_width=1)  # force unit flags
    skel = soul_consolidate.write_skeleton(tmp_path, stats)
    text = skel.read_text(encoding="utf-8")
    # no raw source path of a flagged unit leaks (the unit uid is a path; the leak was 'unit:<path>')
    assert "unit:archive" not in text and "/raw/" not in text and ".tex" not in text
    assert ".txt" not in text  # no source filename at all on the committed surface
