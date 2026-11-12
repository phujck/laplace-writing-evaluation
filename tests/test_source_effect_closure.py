"""Real writer boundaries, not constructor-only source-effect examples."""

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from laplace.manuscript import manuscript_source, manuscript_structure, project_structure
from laplace.manuscript import projection_viewer as pv, review_surface, storyboard
from laplace.native import tools as writing_tools
from laplace.writing import operations
from laplace.manuscript import source_effects
from test_manuscript_structure import _section_fixture


def raw_read(root, file):
    status, _, body = pv.handle(
        "/projection/tex", {"corpus": ["book"], "file": [file], "view": ["source"]}, "GET", b""
    )
    assert status == 200
    return json.loads(body)


def raw_save(read, text):
    query = {key: [value] for key, value in read["save_handle"]["query"].items()}
    query.update(author=["fixture"], bank=["editor"])
    status, _, body = pv.handle("/projection/tex", query, "POST", text.encode())
    return status, json.loads(body)


def test_raw_crlf_multiple_headings_use_indexed_plan_batch_and_restore(tmp_path, monkeypatch):
    manuscript, chapter, _ = _section_fixture(tmp_path)
    chapter.write_bytes(chapter.read_bytes().replace(b"\n", b"\r\n"))
    monkeypatch.setattr(pv, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(review_surface, "_repo_root", lambda: tmp_path)
    file = chapter.relative_to(tmp_path).as_posix()
    original = chapter.read_bytes()
    archived = pv.bank_editor_save(
        manuscript, chapter, original, author="fixture", surface="explicit-archive"
    )
    observed = raw_read(tmp_path, file)
    assert "\r\n" in observed["content"]
    calls = []
    read_ledger = storyboard._read_ledger

    def counted(*args, **kwargs):
        calls.append(inspect.currentframe().f_back.f_code.co_name)
        return read_ledger(*args, **kwargs)

    monkeypatch.setattr(storyboard, "_read_ledger", counted)
    text = (
        observed["content"]
        .replace("{First}", "{First revised}")
        .replace("{First child}", "{Child revised}")
        .replace("{Second}", "{Second revised}")
    )
    status, result = raw_save(observed, text)
    assert status == 200 and chapter.read_bytes() == text.encode()
    effect = result["source_effect"]
    assert effect["state"] == "COMMITTED" and effect["complete"]
    assert effect["follow_through"]["heading_sync"]["status"] == "CURRENT"
    assert calls == []  # M2: indexed checkpoint/tail, no whole-ledger read per heading.
    assert [
        row["title"]
        for row in json.loads((manuscript / "projection_plan.json").read_text())["sections"]
    ] == ["First revised", "Child revised", "Second revised"]
    for handle in effect["impact"]["reads"]:
        operations._execute(tmp_path, "book", "work", handle["operation"], handle["payload"])
    restored = pv.restore_editor_save(
        "book",
        str(chapter),
        archived["version_id"],
        result["expected_source_digest"],
        result["selection_identity"],
    )
    assert chapter.read_bytes() == original
    assert restored["source_effect"]["state"] == "COMMITTED"
    assert restored["source_effect"]["follow_through"]["heading_sync"]["status"] == "CURRENT"
    assert [
        row["title"]
        for row in json.loads((manuscript / "projection_plan.json").read_text())["sections"]
    ] == ["First", "First child", "Second"]


def test_raw_optional_heading_failure_is_committed_and_noop_or_refusal_do_not_repeat(
    tmp_path, monkeypatch
):
    manuscript, chapter, _ = _section_fixture(tmp_path)
    monkeypatch.setattr(pv, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(review_surface, "_repo_root", lambda: tmp_path)
    observed = raw_read(tmp_path, chapter.relative_to(tmp_path).as_posix())

    def fail(*args, **kwargs):
        raise OSError("controlled projection failure")

    monkeypatch.setattr(source_effects, "mirror_headings", fail)
    status, saved = raw_save(observed, observed["content"].replace("{First}", "{New first}"))
    assert status == 200 and saved["source_committed"]
    assert saved["source_effect"]["state"] == "COMMITTED" and saved["source_effect"]["complete"]
    assert saved["source_effect"]["follow_through"]["maintenance_warnings"]
    current = raw_read(tmp_path, chapter.relative_to(tmp_path).as_posix())
    versions = (manuscript / "editor_saves/index.json").read_bytes()
    status, noop = raw_save(current, current["content"])
    assert status == 200 and noop["source_committed"] and not noop["changed"]
    assert noop["source_effect"]["state"] == "UNCHANGED" and noop["source_effect"]["complete"]
    assert (manuscript / "editor_saves/index.json").read_bytes() == versions
    status, refused = raw_save(observed, "stale write")
    assert status == 409 and "source_effect" not in refused


def test_required_section_plan_failure_proves_rollback_and_native_failure_keeps_it(
    tmp_path, monkeypatch
):
    _manuscript, chapter, _ = _section_fixture(tmp_path)
    original = chapter.read_bytes()
    state = project_structure.state("book", tmp_path)
    payload = {
        "operation": "create",
        "source_file": "chapters/chapter-01.tex",
        "after_line": 4,
        "after_before": "Child body.",
        "expected_source_digest": hashlib.sha256(original).hexdigest(),
        "expected_plan_revision": state["revision"],
        "title": "Refused new",
        "kind": "subsection",
    }
    monkeypatch.setattr(
        manuscript_structure,
        "_plan_write",
        lambda *a, **k: {"applied": False, "error": "controlled plan refusal"},
    )
    with pytest.raises(source_effects.SourceEffectFailure) as error:
        manuscript_structure.change("book", payload, tmp_path)
    assert chapter.read_bytes() == original
    effect = error.value.details["source_effect"]
    assert effect["state"] == "ROLLED_BACK" and not effect["complete"]
    assert effect["follow_through"]["required"][0]["status"] == "FAILED"
    failure = writing_tools.failure_response(
        tmp_path, "book", "work", "section_change", payload, error.value
    )
    assert failure["source_effect"] == effect
    assert "repeat" in failure["recovery"]
    saved = writing_tools.bank_failure(tmp_path, "book", "section_change", payload, error.value)
    rows = [
        json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()
    ]
    row = next(row for row in rows if row.get("id") == saved["row_id"])
    assert row["recovery"]["source_effect"] == effect
    assert "source_effect" not in row  # one existing saved recovery envelope, no duplicate copy


def test_failed_before_source_observation_never_constructs_successful_noop(tmp_path, monkeypatch):
    _manuscript, chapter, _ = _section_fixture(tmp_path)
    observed = chapter.read_bytes()
    with pytest.raises(ValueError):
        manuscript_structure.change(
            "book",
            {"operation": "create", "source_file": "missing.tex", "title": "No source"},
            tmp_path,
        )
    assert chapter.read_bytes() == observed
    with pytest.raises(ValueError, match="requires an observed source file"):
        source_effects.receipt("book", None, [], complete=False)


def test_edit_in_place_uses_the_same_heading_followthrough_as_raw_source(tmp_path, monkeypatch):
    manuscript, chapter, _ = _section_fixture(tmp_path)
    monkeypatch.setattr(review_surface, "_repo_root", lambda: tmp_path)
    selected = manuscript_source.observation("book", tmp_path)
    result = review_surface.adjudicate(
        manuscript,
        "book",
        {
            "verb": "edit-in-place",
            "by": "fixture",
            "section": "first",
            "file": chapter.relative_to(manuscript).as_posix(),
            "before": r"\chapter{First}",
            "after": r"\chapter{First edited}",
            "expected_selection": selected["selection_identity"],
        },
        repo_root=tmp_path,
    )
    assert result.get("ok"), result
    assert result["source_effect"]["state"] == "COMMITTED"
    assert result["source_effect"]["follow_through"]["heading_sync"]["status"] == "CURRENT"
    assert (
        json.loads((manuscript / "projection_plan.json").read_text())["sections"][0]["title"]
        == "First edited"
    )


def test_block_source_commit_survives_required_inverse_record_failure(tmp_path, monkeypatch):
    from laplace.manuscript import blocks as manuscript_blocks
    from laplace.core.records import journal
    from test_manuscript_blocks import _fixture, _digest

    source, figure = _fixture(tmp_path)
    main, other = source / "chapter.tex", source / "other.tex"
    bank = journal.bank_row

    def fail(path, row, **kwargs):
        if row.get("record") == "manuscript-block-change":
            raise OSError("controlled inverse tracking failure")
        return bank(path, row, **kwargs)

    monkeypatch.setattr(journal, "bank_row", fail)
    with pytest.raises(source_effects.SourceEffectFailure) as error:
        manuscript_blocks.change(
            tmp_path,
            "blocks",
            {
                "operation": "move",
                "block": {
                    "file": "chapter.tex",
                    "line_start": 2,
                    "line_end": 7,
                    "before": figure,
                    "expected_source_digest": _digest(main),
                },
                "destination": {
                    "file": "other.tex",
                    "line": 1,
                    "before": "Other anchor.",
                    "expected_source_digest": _digest(other),
                },
            },
        )
    effect = error.value.details["source_effect"]
    assert effect["state"] == "COMMITTED" and not effect["complete"]
    assert figure not in main.read_text() and figure in other.read_text()
    assert len(effect["files"]) == 2


def test_required_failure_cannot_be_acknowledged_by_default_completion_flag(tmp_path):
    path = tmp_path / "source.tex"
    path.write_bytes(b"Published source.\n")
    observed = source_effects.observed_file(tmp_path, path, b"Prior source.\n", path.read_bytes())
    for status in ("FAILED", "UNPROVED", "COMPENSATED"):
        effect = source_effects.receipt(
            "fixture",
            "sha256:" + "a" * 64,
            [observed],
            required=[{"owner": "required-domain-step", "status": status}],
        )
        assert effect["state"] == "COMMITTED"
        assert effect["complete"] is False
    with pytest.raises(ValueError, match="unknown required"):
        source_effects.receipt(
            "fixture", None, [observed], required=[{"owner": "plan", "status": "probably done"}]
        )


def test_empty_io_error_is_unproved_physical_observation(tmp_path, monkeypatch):
    path = tmp_path / "source.tex"
    path.write_bytes(b"Published source.\n")
    read = Path.read_bytes

    def unreadable(target):
        if target == path:
            raise OSError()
        return read(target)

    monkeypatch.setattr(Path, "read_bytes", unreadable)
    row = source_effects.observed_file(tmp_path, path, b"Prior source.\n", b"Published source.\n")
    assert row["observation_error"] == ""
    effect = source_effects.receipt("fixture", "sha256:" + "a" * 64, [row])
    assert effect["state"] == "UNPROVED" and not effect["complete"]


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_chapter_root_swap_failure_reports_final_files_and_admissible_reads(
    tmp_path, monkeypatch, cleanup_fails
):
    from test_manuscript_structure import _book

    manuscript = _book(tmp_path)
    main = manuscript / "Fixture-Book.tex"
    chapter = manuscript / "chapters" / "retained-chapter.tex"
    before = main.read_bytes()
    replace, unlink = Path.replace, Path.unlink

    def fail_swap(path, destination):
        if Path(destination) == main:
            raise OSError("controlled root swap failure")
        return replace(path, destination)

    def cleanup(path, *args, **kwargs):
        if path == chapter and cleanup_fails:
            raise OSError("controlled created-file cleanup failure")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "replace", fail_swap)
    monkeypatch.setattr(Path, "unlink", cleanup)
    with pytest.raises(source_effects.SourceEffectFailure) as error:
        manuscript_structure.create_chapter("book", "Retained chapter", tmp_path)
    effect = error.value.details["source_effect"]
    assert main.read_bytes() == before and chapter.exists() is cleanup_fails
    assert effect["state"] == ("PARTIAL" if cleanup_fails else "ROLLED_BACK")
    assert not effect["complete"] and len(effect["files"]) == 2
    if cleanup_fails:
        assert (
            effect["impact"]["source_read_omissions"][0]["file"]
            == chapter.relative_to(tmp_path).as_posix()
        )
    for handle in effect["impact"]["reads"]:
        operations._execute(tmp_path, "book", "work", handle["operation"], handle["payload"])
