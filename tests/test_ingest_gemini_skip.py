"""The Gemini pipe must not pay for an export of a meeting the collection already holds.

Regression for 2026-10-08: the directory-name check re-exported every old meeting because
sessions rename call directories and Drive moved the folder. The identity is the doc's filename
read from the extraction's provenance line; date+slug and the ledger are fallbacks.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

AUTHORED = "Jack+Andrew - 2026／08／12 08:28 BST - Notes by Gemini.docx"
QUEUED = "Andrew - 2026／07／30 10:57 BST - Notes by Gemini.docx"
BY_NAME = "Andrew - 2026／08／10 16:44 BST - Notes by Gemini.docx"
LEDGERED = "Roger - 2026／08／14 16:41 BST - Notes by Gemini.docx"
FRESH = "Board - 2026／10／09 09:00 BST - Notes by Gemini.docx"
FOLDER = "gdrive:Google Meet/Meet Recordings/"


def _pipe():
    spec = importlib.util.spec_from_file_location("ingest_gemini", REPO / "scripts" / "ingest_gemini.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tree(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path
    ev = repo / "evidence"
    queue = ev / "intake_queue"
    # Authored under a session-chosen name; its line recorded the OLD Drive folder.
    d = ev / "call_2026-08-12_jack-hampson-andrew-graham"
    d.mkdir(parents=True)
    (d / "extraction.md").write_text(
        f"- Source: Google Doc exported via rclone from `gdrive:Meet Recordings/{AUTHORED}`.\n",
        encoding="utf-8")
    # A stub still waiting in the queue, written by the pipe.
    q = queue / "call_2026-07-30_andrew"
    q.mkdir(parents=True)
    (q / "extraction.md").write_text(
        f"- Source: Google Doc exported via rclone from `{FOLDER}{QUEUED}`.\n", encoding="utf-8")
    # A directory by the machine name whose extraction names no doc at all.
    (ev / "call_2026-08-10_andrew").mkdir()
    (ev / "call_2026-08-10_andrew" / "extraction.md").write_text("# authored elsewhere\n", encoding="utf-8")
    return repo, queue


def test_renamed_directory_and_moved_folder_still_count_as_in_the_collection(tmp_path):
    pipe = _pipe()
    repo, queue = _tree(tmp_path)
    index = pipe.collection_index(repo, queue)
    assert set(index) == {AUTHORED, QUEUED}

    state, detail = pipe.disposition(FOLDER + AUTHORED, index, {}, repo, queue)
    assert state == "collection"
    assert "call_2026-08-12_jack-hampson-andrew-graham" in detail

    state, detail = pipe.disposition(FOLDER + QUEUED, index, {}, repo, queue)
    assert state == "queued"
    assert "intake_queue/call_2026-07-30_andrew" in detail


def test_fallbacks_and_genuinely_new(tmp_path):
    pipe = _pipe()
    repo, queue = _tree(tmp_path)
    index = pipe.collection_index(repo, queue)

    state, detail = pipe.disposition(FOLDER + BY_NAME, index, {}, repo, queue)
    assert state == "collection" and "date+slug" in detail

    ledger = {FOLDER + LEDGERED: {"size": 1, "mtime": 1, "target": "call_2026-08-14_roger"}}
    assert pipe.disposition(FOLDER + LEDGERED, index, ledger, repo, queue)[0] == "ledger"

    assert pipe.disposition(FOLDER + FRESH, index, ledger, repo, queue) is None


def test_collection_wins_over_a_duplicate_still_in_the_queue(tmp_path):
    pipe = _pipe()
    repo, queue = _tree(tmp_path)
    dup = queue / "call_2026-08-12_jackandrew"
    dup.mkdir()
    (dup / "extraction.md").write_text(
        f"- Source: Google Doc exported via rclone from `{FOLDER}{AUTHORED}`.\n", encoding="utf-8")
    index = pipe.collection_index(repo, queue)
    assert index[AUTHORED][0] == "collection"
