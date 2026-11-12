"""The verbatim floor of MY record (the weld, slice 1), pinned.

Contracts: chunks are exact char ranges of the committed source (recovery = re-read, round-trip
identical, never a paraphrase); the day token welds the diary's entry to that day's handoffs;
atoms ride the keeper as ``::`` leaves under their (authored) file node; the scanner's content
route serves the verbatim range with its locator."""

from __future__ import annotations

from laplace.engine import keeper, record_shard


def test_record_inventory_excludes_ignored_sandboxes_and_fixture_sessions(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(".pytest-tmp/\n")
    for relative in ("SESSION_HANDOFF_2026-09-19_live.md",
                     ".pytest-tmp/case/SESSION_HANDOFF_2026-09-19_fake.md",
                     "tests/fixtures/SESSION_HANDOFF_2026-09-19_fixture.md",
                     "archive/SESSION_HANDOFF_2026-09-19_copy.md"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# A record\nThis must be classified by provenance.\n")
    assert record_shard.record_sources(tmp_path) == ["SESSION_HANDOFF_2026-09-19_live.md"]


def _seed(tmp_path):
    (tmp_path / "SESSION_HANDOFF_2026-06-08_eating-the-dump.md").write_text(
        "# Session handoff\n\nthe arc of the day.\n\n## The bite\n\nwe ate the dump.\n\n"
        "## Next\n\nthe upward operator.\n", encoding="utf-8")
    (tmp_path / "EIGEN_DIARY.md").write_text(
        "# Eigen diary\n\npreface line.\n\n## 2026-06-08 - The day of the dump\n\n"
        "I built the thing that eats without exposing.\n", encoding="utf-8")


def test_chunks_are_exact_ranges_and_round_trip(tmp_path):
    _seed(tmp_path)
    floor = record_shard.build_floor(tmp_path)
    text = (tmp_path / "EIGEN_DIARY.md").read_text(encoding="utf-8")
    for sh in floor:
        if sh["source"] != "EIGEN_DIARY.md":
            continue
        body = record_shard.reconstruct(tmp_path, sh["id"], floor)
        assert body == text[sh["start"]:sh["end"]]          # verbatim: the exact committed slice
    labels = [sh["label"] for sh in floor if sh["source"] == "EIGEN_DIARY.md"]
    assert any("2026-06-08" in lb for lb in labels)          # sections cut at headings


def test_day_token_welds_diary_to_handoff(tmp_path):
    # the first weld wire: the diary's entry and that day's handoff share recdate::<day>
    _seed(tmp_path)
    idx = record_shard.record_edge_index(tmp_path)
    handoff_toks = {t for aid, ts in idx.items() if aid.startswith("SESSION_HANDOFF") for t in ts}
    diary_toks = {t for aid, ts in idx.items() if aid.startswith("EIGEN_DIARY") for t in ts}
    assert "recdate::2026-06-08" in handoff_toks & diary_toks
    assert any(t.startswith("inrecord::") for t in handoff_toks)   # structural referent present


def test_oversize_section_subsplits_with_heading_kept():
    text = "## big section\n\n" + ("para.\n\n" * 4000)            # >> 1.5 * target
    chunks = record_shard.chunk_md(text)
    assert len(chunks) > 1
    assert all("big section" in lb for _a, _b, lb in chunks)
    assert chunks[0][0] == 0 and chunks[-1][1] == len(text)        # full cover, no gaps at ends
    for (_a, b, _), (a2, _b2, _2) in zip(chunks, chunks[1:], strict=False):
        assert b == a2                                             # contiguous ranges


def test_headingless_text_falls_back_to_paragraphs():
    chunks = record_shard.chunk_md("plain text\n\nwith paragraphs\n")
    assert chunks and chunks[0][2].startswith("para:")


def test_atoms_ride_the_keeper_under_authored_files(tmp_path):
    # the integration shape build_self uses: file leaves + atom leaves + the universal :: parent
    from laplace.engine import concept_lens
    _seed(tmp_path)
    leaves = {
        "SESSION_HANDOFF_2026-06-08_eating-the-dump.md":
            {"kind": "md", "essence": "Session handoff - the soul pour began", "keywords": ["soul"]},
        "EIGEN_DIARY.md":
            {"kind": "md", "essence": "Eigen diary - the self-model", "keywords": ["diary"]},
    }
    leaves.update(record_shard.floor_leaves(tmp_path))

    def parent_of(nid):
        ap = concept_lens.atom_parent(nid)
        if ap is not None:
            return ap
        return keeper.series_parent(nid) or keeper.dir_parent(nid)

    nodes = keeper.build_tree(leaves, parent_of)
    handoff = nodes["SESSION_HANDOFF_2026-06-08_eating-the-dump.md"]
    assert handoff["leaf"] is False and handoff["grade"] == 1      # the file rose: atoms below it
    assert handoff["authored"] is True
    assert handoff["essence"] == "Session handoff - the soul pour began"   # kept, not summarised
    assert all(m.startswith("SESSION_HANDOFF_2026-06-08") and "::" in m
               for m in handoff["members"])
    assert nodes[handoff["parent"]]["id"] == keeper.HANDOFF_SERIES  # and the series above it
    assert nodes[keeper.HANDOFF_SERIES]["grade"] == 2
    assert keeper.local_faithfulness(nodes)["pass"] is True


def test_atom_content_serves_verbatim_with_locator(tmp_path):
    _seed(tmp_path)
    record_shard.write_floor(tmp_path, record_shard.build_floor(tmp_path))
    floor = record_shard.load_floor(tmp_path)
    aid = next(sh["id"] for sh in floor if sh["label"] == "The bite")
    out = record_shard.atom_content(tmp_path, aid)
    assert out["kind"] == "record-atom"
    assert "we ate the dump." in out["content"]
    assert out["locator"].startswith("SESSION_HANDOFF_2026-06-08_eating-the-dump.md#")
    assert out["date"] == "2026-06-08"
    assert record_shard.atom_content(tmp_path, "no/such.md::9") is None


def _seed_sessions(tmp_path):
    import json as _json
    src = tmp_path / "src_sessions"
    src.mkdir()
    events = [
        {"type": "queue-operation", "operation": "enqueue", "content": "noise"},
        {"type": "user", "userType": "external", "timestamp": "2026-06-10T08:00:00.000Z",
         "message": {"role": "user", "content": "hello Eigen, the big day"}},
        {"type": "assistant",
         "message": {"role": "assistant", "content": [
             {"type": "thinking", "thinking": "private reasoning"},
             {"type": "text", "text": "Morning Gerard."},
             {"type": "tool_use", "name": "Bash", "input": {}}]}},
        {"type": "user", "isSidechain": True,
         "message": {"role": "user", "content": "subagent noise"}},
        {"type": "user", "userType": "external",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "content": "machine traffic"},
             {"type": "text", "text": "<system-reminder>harness noise</system-reminder>"}]}},
        {"type": "user", "userType": "external", "timestamp": "2026-06-10T09:00:00.000Z",
         "message": {"role": "user", "content": "go brrr"}},
    ]
    (src / "abc123.jsonl").write_text(
        "\n".join(_json.dumps(e) for e in events), encoding="utf-8")
    return src


def test_explode_sessions_keeps_dialogue_drops_machine(tmp_path):
    src = _seed_sessions(tmp_path)
    assert record_shard.land_sessions(tmp_path, source_dir=src)
    written = record_shard.explode_sessions(tmp_path)
    assert written == ["archive/self_record/_exploded/session_abc123.txt"]
    text = (tmp_path / written[0]).read_text(encoding="utf-8")
    assert "@@Gerard\nhello Eigen, the big day" in text
    assert "@@Eigen  [+1 tool calls]\nMorning Gerard." in text
    assert "@@Gerard\ngo brrr" in text
    assert "private reasoning" not in text                 # thinking stays in the raw only
    assert "subagent noise" not in text                    # sidechains are machine traffic
    assert "harness noise" not in text                     # system reminders are not his voice
    assert "turns: g2 e1" in text and "2026-06-10" in text


def test_chunk_dialogue_breaks_at_turns_with_named_counts():
    text = "@@Gerard\n" + ("question " * 800) + "\n\n@@Eigen\n" + ("answer " * 800) + "\n\n@@Gerard\nshort\n"
    chunks = record_shard.chunk_dialogue(text)
    assert len(chunks) > 1
    assert all(lb.startswith("turns:") for _a, _b, lb in chunks)
    assert "g" in chunks[0][2] and "e" in chunks[0][2]      # the his/mine split is visible
    for (_a, b, _l), (a2, _b2, _l2) in zip(chunks, chunks[1:], strict=False):
        assert b == a2                                      # never splits a turn, never gaps


def test_transcript_floor_is_sealed_and_serves_locally(tmp_path):
    src = _seed_sessions(tmp_path)
    record_shard.land_sessions(tmp_path, source_dir=src)
    record_shard.explode_sessions(tmp_path)
    floor = record_shard.build_floor(tmp_path)
    t_entries = [e for e in floor if e["source"].startswith("archive/self_record")]
    assert t_entries and all(e["sealed"] for e in t_entries)
    assert all(e["date"] == "2026-06-10" for e in t_entries)
    # the network leaves exclude the dialogue floor (session granularity carries it)...
    assert not any(lid.startswith("archive/self_record") for lid in record_shard.floor_leaves(tmp_path))
    # ...but the local display still serves the verbatim turn window, marked sealed
    record_shard.write_floor(tmp_path, floor)
    first_turns = next(e for e in t_entries if e["label"].startswith("turns:"))
    out = record_shard.atom_content(tmp_path, first_turns["id"])
    assert out["sealed"] is True and "hello Eigen, the big day" in out["content"]


def test_transcript_leaves_are_content_free_handles(tmp_path):
    src = _seed_sessions(tmp_path)
    record_shard.land_sessions(tmp_path, source_dir=src)
    record_shard.explode_sessions(tmp_path)
    leaves = record_shard.transcript_leaves(tmp_path)
    rel = "archive/self_record/_exploded/session_abc123.txt"
    assert rel in leaves and leaves[rel]["sealed"] is True
    assert "g2 e1" in leaves[rel]["essence"] and "2026-06-10" in leaves[rel]["essence"]
    assert "hello" not in leaves[rel]["essence"]            # not a word of dialogue in the handle
    assert record_shard.transcript_parent(rel) == record_shard.TRANSCRIPT_SERIES
    assert record_shard.transcript_parent(rel + "::0") is None
    # the weld wire at session granularity: the transcript couples to the day it records
    idx = record_shard.transcript_edge_index(tmp_path)
    assert "recdate::2026-06-10" in idx[rel]
    # and the series folds sealed in the keeper
    nodes = keeper.build_tree(
        leaves, lambda nid: record_shard.transcript_parent(nid) or keeper.dir_parent(nid))
    series = nodes[record_shard.TRANSCRIPT_SERIES]
    assert series["grade"] == 1 and series["sealed"] is True and series["parent"] == ""
