"""Tests for soul_shard - the sealed deep-sharder for the soul dump.

No real soul content here: a synthetic tmp tree stands in for archive/soul_dump/raw/. The contract
under test is the one the author's correction demands - the detail is RECOVERABLE from the shard
(reconstruct returns the exact source range), and soul-class never travels (reconstruct returns ""
when the raw is absent, so a fresh clone recovers nothing)."""

from __future__ import annotations

from pathlib import Path

from laplace.engine import soul_shard


def _raw(tmp_path: Path) -> Path:
    raw = tmp_path / "archive" / "soul_dump" / "raw"
    (raw / "personal_writing" / "piece").mkdir(parents=True)
    (raw / "chat_logs" / "friend").mkdir(parents=True)
    # a sectioned tex piece -> chunks at \section
    (raw / "personal_writing" / "piece" / "main.tex").write_text(
        "\\section{One}\nalpha body\n\\section{Two}\nbeta body\n", encoding="utf-8")
    # a whatsapp-shaped txt -> line-window chunks (timestamped first line triggers the chat chunker)
    (raw / "chat_logs" / "friend" / "WhatsApp Chat with friend.txt").write_text(
        "\n".join(f"[01/02/2020, 1{i%6}:30] role: message {i}" for i in range(300)), encoding="utf-8")
    return raw


def test_shard_chunks_by_format_and_categorises(tmp_path):
    _raw(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    cats = {s["category"] for s in shards}
    assert cats == {"personal_writing", "chat_logs"}
    tex = [s for s in shards if s["kind"] == "tex"]
    assert len(tex) >= 2  # split at the two \section heads
    assert any(s["label"].startswith("tex:") for s in tex)


def test_reconstruct_returns_exact_source_range(tmp_path):
    _raw(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    for sh in shards:
        if sh["end"] <= sh["start"]:
            continue
        text = soul_shard.reconstruct(tmp_path, sh["id"], shards)
        assert len(text) == sh["n_chars"]  # the detail is recoverable, to the character


def test_reconstruct_returns_empty_when_raw_absent(tmp_path):
    """Soul-class never travels: with no raw on disk, the shard recovers nothing."""
    _raw(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    a_chunk = next(s for s in shards if s["end"] > s["start"])
    # simulate a fresh clone: index entries exist, the raw does not
    import shutil
    shutil.rmtree(tmp_path / "archive" / "soul_dump" / "raw")
    assert soul_shard.reconstruct(tmp_path, a_chunk["id"], shards) == ""


def test_local_index_roundtrips(tmp_path):
    _raw(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    soul_shard.write_local_index(tmp_path, shards)
    back = soul_shard.load_local_index(tmp_path)
    assert {s["id"] for s in back} == {s["id"] for s in shards}


def test_manifest_is_structural_only(tmp_path):
    _raw(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    man = soul_shard.manifest(shards)
    assert man["chunks"] == len(shards)
    assert set(man["by_category"]) == {"personal_writing", "chat_logs"}
    # the manifest carries counts + axis names only - never content
    assert "axes_discovered" in man
    blob = repr(man)
    assert "message 1" not in blob and "alpha body" not in blob


# ---------------------------------------------------------------------------
# the Claude-chat dialogue path (MOVE-1): explode -> speaker-tagged transcripts -> turn-windows
# ---------------------------------------------------------------------------

def _claude_export(tmp_path: Path) -> Path:
    """A synthetic Claude export: one empty conversation (dropped), one small, one large enough to
    window into >=2 turn-chunks. SECRET tokens stand in for soul content - they must never surface
    in a shard label or the structural manifest, only in the gitignored transcript range."""
    import json
    raw = tmp_path / "archive" / "soul_dump" / "raw" / "claude_chats"
    raw.mkdir(parents=True)
    big = [{"sender": "human" if i % 2 == 0 else "assistant",
            "text": f"SECRET_TURN_{i} " + "lorem ipsum dolor sit amet " * 30,
            "attachments": [], "files": []} for i in range(40)]
    export = [
        {"name": "EMPTY", "created_at": "2020", "chat_messages": []},
        {"name": "SECRET_TITLE_small", "created_at": "2021",
         "chat_messages": [{"sender": "human", "text": "SECRET_hi", "attachments": [], "files": []},
                           {"sender": "assistant", "text": "SECRET_hello", "attachments": [], "files": []}]},
        {"name": "big", "created_at": "2022", "chat_messages": big},
    ]
    (raw / "conversations.json").write_text(json.dumps(export), encoding="utf-8")
    return raw


def test_dialogue_explodes_to_speaker_tagged_transcripts(tmp_path):
    _claude_export(tmp_path)
    written = soul_shard.build_dialogue_transcripts(tmp_path)
    # empty conversation dropped; two real ones exploded, index-named, deterministic
    assert sorted(Path(w).name for w in written) == ["conv_0001.txt", "conv_0002.txt"]
    small = (tmp_path / written[0]).read_text(encoding="utf-8")
    assert "@@Gerard" in small and "@@Assistant" in small  # human = the author = signal


def test_dialogue_shards_window_at_turns_and_source_is_asset(tmp_path):
    _claude_export(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    # the 91MB-style source blob is NOT generic-chunked: one asset node, exploded note
    src = [s for s in shards if s["source"].endswith("conversations.json")]
    assert len(src) == 1 and src[0]["label"].startswith("dialogue source")
    # the big conversation windowed into >=2 turn-chunks, each labelled with the his/other split
    dlg = [s for s in shards if "conv_0002" in s["source"]]
    assert len(dlg) >= 2
    assert all(s["label"].startswith(("turns:", "header")) for s in dlg)
    assert any("g" in s["label"] and "o" in s["label"] for s in dlg)


# ---------------------------------------------------------------------------
# materialized-output dedup (WO-20260820-chat-shard-dedup): content-hash identity across ANY
# existing _shard/*/ staging directory, so a chunk already materialized once is never duplicated
# under a second directory - the FIBRE_CENSUS 2026-08-19 failure (422 duplicate leaves, claude_smoke
# vs scaled_claude) reproduced small and proven fixed.
# ---------------------------------------------------------------------------

def test_content_hash_is_stable_and_distinguishes_content():
    assert soul_shard.content_hash("alpha") == soul_shard.content_hash("alpha")
    assert soul_shard.content_hash("alpha") != soul_shard.content_hash("beta")


def test_materialized_index_finds_existing_chunks_across_output_dirs(tmp_path):
    shard_root = tmp_path / "archive" / "soul_dump" / "_shard"
    smoke = shard_root / "claude_smoke"
    smoke.mkdir(parents=True)
    (smoke / "conv_0001.txt_0.txt").write_text("@@Gerard\nhello\n", encoding="utf-8")
    (smoke / "_manifest.json").write_text("[]", encoding="utf-8")  # never treated as a chunk

    idx = soul_shard.materialized_index(tmp_path)
    assert soul_shard.content_hash("@@Gerard\nhello\n") in idx
    assert idx[soul_shard.content_hash("@@Gerard\nhello\n")] == "archive/soul_dump/_shard/claude_smoke/conv_0001.txt_0.txt"


def test_materialized_index_absent_shard_root_returns_empty(tmp_path):
    assert soul_shard.materialized_index(tmp_path) == {}


def test_materialized_index_empty_directory_reduces_duplicate_count_to_zero(tmp_path):
    """The exact regression: the same chunk staged under two directories collapses to ONE
    canonical path once the second staging checks materialized_index first (the fixed producer's
    contract), instead of writing a byte-identical second copy."""
    shard_root = tmp_path / "archive" / "soul_dump" / "_shard"
    scaled = shard_root / "scaled_claude"
    scaled.mkdir(parents=True)
    text = "@@Gerard\nSECRET_TURN_1\n"
    (scaled / "conv_0135.txt_10.txt").write_text(text, encoding="utf-8")

    # BEFORE the fix (what the archived stager used to do): a second staging step writes the
    # identical text into a fresh directory unconditionally -> a duplicate leaf on disk.
    smoke = shard_root / "claude_smoke"
    smoke.mkdir(parents=True)
    duplicates_written_naively = 0
    (smoke / "conv_0135.txt_10.txt").write_text(text, encoding="utf-8")
    duplicates_written_naively += 1
    assert duplicates_written_naively == 1  # the pre-fix failure mode, reproduced

    # AFTER the fix: materialized_index sees the already-staged content and the caller skips the
    # write instead of duplicating it - the dedup contract stage_tranche.stage() now honours.
    # Exactly ONE canonical path survives per content hash, whichever staging landed first
    # (rglob's sort order) - the point is there is one, not which directory owns it.
    idx = soul_shard.materialized_index(tmp_path)
    h = soul_shard.content_hash(text)
    assert h in idx
    assert idx[h] in ("archive/soul_dump/_shard/scaled_claude/conv_0135.txt_10.txt",
                      "archive/soul_dump/_shard/claude_smoke/conv_0135.txt_10.txt")


def test_dialogue_labels_never_leak_content(tmp_path):
    _claude_export(tmp_path)
    shards = soul_shard.shard_tree(tmp_path)
    blob = repr([{k: s[k] for k in ("id", "label", "category", "kind")} for s in shards])
    assert "SECRET" not in blob  # not in ids, labels, categories
    man = soul_shard.manifest(shards)
    assert "SECRET" not in repr(man)
    # but the detail IS recoverable from the sealed range
    dlg = next(s for s in shards if "conv_0002" in s["source"] and s["label"].startswith("turns:"))
    assert "SECRET_TURN" in soul_shard.reconstruct(tmp_path, dlg["id"], shards)
