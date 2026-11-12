from __future__ import annotations
from laplace.manuscript import manuscript_source as source_owner

import hashlib
import json
from pathlib import Path
import threading

import pytest

from laplace.manuscript import manuscript_source, manuscript_structure as structure
from laplace.projects import library as writing_projects


def _book(root: Path, name="book") -> Path:
    status, result = writing_projects.create({"name": name, "title": "Fixture Book", "kind": "book"}, root)
    assert status == 201, result
    return root / "synthetics papers" / name / "manuscript"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _section_fixture(root: Path) -> tuple[Path, Path, dict]:
    manuscript = _book(root)
    chapter = manuscript / "chapters" / "chapter-01.tex"
    chapter.write_text(
        "\\chapter{First}\nFirst body.\n\\section{First child}\nChild body.\n"
        "\\chapter{Second}\nSecond body.\n", encoding="utf-8")
    plan_path = manuscript / "projection_plan.json"
    plan = json.loads(plan_path.read_text())
    plan["sections"] = [
        {"id": "first", "title": "First", "kind": "chapter", "parent_id": None,
         "source_file": "chapters/chapter-01.tex", "job": "open", "notes": "",
         "refs": [], "beats": [], "nodes_in_order": ["concept:first"], "figures": []},
        {"id": "first-child", "title": "First child", "kind": "section", "parent_id": "first",
         "source_file": "chapters/chapter-01.tex", "job": "support", "notes": "",
         "refs": [], "beats": [], "nodes_in_order": [], "figures": []},
        {"id": "second", "title": "Second", "kind": "chapter", "parent_id": None,
         "source_file": "chapters/chapter-01.tex", "job": "close", "notes": "",
         "refs": [], "beats": [], "nodes_in_order": [], "figures": []},
    ]
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n")
    return manuscript, chapter, plan


def test_real_book_create_empty_escaped_chapter_and_all_receipts(tmp_path):
    manuscript = _book(tmp_path)
    main = manuscript / "Fixture-Book.tex"
    main.write_text(main.read_text().replace("\\documentclass{book}", "\\documentclass[11pt]{book}"))
    before = hashlib.sha256(main.read_bytes()).hexdigest()

    result = structure.create_chapter(
        "book", r"First & Second_# $ {Draft}", tmp_path, expected_root_digest=before)

    chapter = tmp_path / result["file"]
    text = chapter.read_text(encoding="utf-8")
    assert result["receipt"]["kind"] == "chapter"
    assert text.startswith(r"\chapter{First \& Second\_\# \$ \{Draft\}}")
    assert text.endswith("\n\n")
    assert "Draft —" not in text and "ready for authoring" not in text
    main_text = main.read_text(encoding="utf-8")
    argument = chapter.relative_to(manuscript).with_suffix("").as_posix()
    assert f"\\input{{{argument}}}" in main_text
    assert main_text.index(f"\\input{{{argument}}}") < main_text.index("\\bibliography")
    traversal = manuscript_source.traversal(
        "synthetics papers/book/manuscript/Fixture-Book.tex", repo_root=tmp_path)
    assert result["file"] in traversal["files"]

    talk = _rows(tmp_path / "contract" / "talk.jsonl")
    intent = next(row for row in talk if row.get("record") == "manuscript-structure")
    complete = next(row for row in talk if row.get("record") == "manuscript-structure-complete")
    assert intent["before"]["root"] and intent["after"]["chapter"] == text
    assert complete["supersedes"] == intent["id"] and len(complete["versions"]) == 2
    feedback = _rows(manuscript / "feedback" / "feedback.jsonl")
    assert any(row.get("kind") == "author-structure" and row.get("anchor", {}).get("created_file") == result["file"]
               for row in feedback)
    saves = json.loads((manuscript / "editor_saves" / "index.json").read_text())["saves"]
    assert {row["file"] for row in saves[-2:]} == {"Fixture-Book.tex", chapter.name}


def test_expected_root_digest_and_read_only_source_refuse_without_writes(tmp_path):
    manuscript = _book(tmp_path)
    main = manuscript / "Fixture-Book.tex"
    before = main.read_bytes()
    with pytest.raises(ValueError, match="changed"):
        structure.create_chapter("book", "Stale", tmp_path, expected_root_digest="0" * 64)
    assert main.read_bytes() == before and not (manuscript / "chapters" / "stale.tex").exists()

    foreign = tmp_path / "foreign"
    foreign.mkdir()
    source = foreign / "main.tex"
    source.write_text("\\documentclass{report}\n\\begin{document}\n\\end{document}\n")
    status, result = writing_projects.import_source(
        {"name": "readonly", "title": "Readonly", "root": "foreign/main.tex"}, tmp_path)
    assert status == 201, result
    with pytest.raises(ValueError, match="read-only"):
        structure.create_chapter("readonly", "Forbidden", tmp_path)
    assert list(foreign.iterdir()) == [source]


def test_report_class_with_options_creates_empty_chapter(tmp_path):
    manuscript = _book(tmp_path)
    main = manuscript / "Fixture-Book.tex"
    main.write_text(main.read_text().replace("\\documentclass{book}",
                                             "\\documentclass[twoside,11pt]{report}"))

    result = structure.create_chapter("book", "Report Chapter", tmp_path)

    assert result["receipt"]["kind"] == "chapter"
    assert (tmp_path / result["file"]).read_text().startswith("\\chapter{Report Chapter}\n")


def test_chapter_collision_is_serialized_inside_file_lock(tmp_path):
    manuscript = _book(tmp_path)
    barrier = threading.Barrier(3)
    results, errors = [], []

    def create():
        barrier.wait()
        try:
            results.append(structure.create_chapter("book", "Concurrent Chapter", tmp_path))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=create) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=10)

    assert len(results) == 1 and len(errors) == 1
    assert "exists" in str(errors[0]) or "already included" in str(errors[0])
    assert (manuscript / "Fixture-Book.tex").read_text().count("\\input{chapters/concurrent-chapter}") == 1
    assert (manuscript / "chapters" / "concurrent-chapter.tex").is_file()


def test_failed_main_swap_rolls_back_only_unchanged_created_chapter(tmp_path, monkeypatch):
    manuscript = _book(tmp_path)
    main = manuscript / "Fixture-Book.tex"
    before = main.read_bytes()
    real_replace = structure.os.replace

    def fail_main(source, destination):
        if Path(destination) == main:
            raise OSError("planted main replacement failure")
        return real_replace(source, destination)

    monkeypatch.setattr(structure.os, "replace", fail_main)
    from laplace.manuscript.source_effects import SourceEffectFailure
    with pytest.raises(SourceEffectFailure, match="planted"):
        structure.create_chapter("book", "Rollback Chapter", tmp_path)

    assert main.read_bytes() == before
    assert not (manuscript / "chapters" / "rollback-chapter.tex").exists()
    assert any(row.get("record") == "manuscript-structure"
               for row in _rows(tmp_path / "contract" / "talk.jsonl"))
    assert not any(row.get("record") == "manuscript-structure-complete"
                   for row in _rows(tmp_path / "contract" / "talk.jsonl"))


def test_delete_and_receipt_restore_exact_source_span_and_plan_membership(tmp_path):
    manuscript, chapter, original_plan = _section_fixture(tmp_path)
    original_source = chapter.read_bytes()
    from laplace.manuscript import project_structure
    state = project_structure.state("book", tmp_path)

    deleted = structure.change("book", {
        "operation": "delete", "section_id": "first",
        "expected_source_digest": hashlib.sha256(original_source).hexdigest(),
        "expected_plan_revision": state["revision"],
    }, tmp_path)

    assert deleted["ok"] and deleted["receipt"]["section_id"] == "first"
    assert chapter.read_text() == "\\chapter{Second}\nSecond body.\n"
    reduced = json.loads((manuscript / "projection_plan.json").read_text())
    assert [row["id"] for row in reduced["sections"]] == ["second"]
    assert deleted["undo"]["receipt_id"] == deleted["receipt"]["id"]

    restored = structure.change("book", deleted["undo"], tmp_path)

    assert restored["ok"] and restored["receipt"]["restored_from"] == deleted["receipt"]["id"]
    assert chapter.read_bytes() == original_source
    assert json.loads((manuscript / "projection_plan.json").read_text()) == original_plan
    saves = json.loads((manuscript / "editor_saves" / "index.json").read_text())["saves"]
    assert [row["source"].split(":", 1)[0] for row in saves[-3:]] == [
        "section-delete-recovery", "section-delete", "section-restore"]


def test_restore_preserves_non_overlapping_source_edit(tmp_path):
    manuscript, chapter, _plan = _section_fixture(tmp_path)
    from laplace.manuscript import project_structure
    state = project_structure.state("book", tmp_path)
    deleted = structure.change("book", {
        "operation": "delete-section", "section_id": "first",
        "expected_source_digest": hashlib.sha256(chapter.read_bytes()).hexdigest(),
        "expected_plan_revision": state["revision"],
    }, tmp_path)
    plan_after_delete = (manuscript / "projection_plan.json").read_bytes()
    chapter.write_text(chapter.read_text().replace("Second body.", "Second revised body."))

    restored = structure.change("book", deleted["undo"], tmp_path)

    assert restored["ok"]
    assert chapter.read_text().endswith("\\chapter{Second}\nSecond revised body.\n")
    assert "\\chapter{First}\nFirst body." in chapter.read_text()
    assert (manuscript / "projection_plan.json").read_bytes() != plan_after_delete


def test_restore_rejects_edit_inside_deleted_gap_without_changing_plan(tmp_path):
    manuscript, chapter, _plan = _section_fixture(tmp_path)
    from laplace.manuscript import project_structure
    state = project_structure.state("book", tmp_path)
    deleted = structure.change("book", {
        "operation": "delete", "section_id": "first",
        "expected_source_digest": hashlib.sha256(chapter.read_bytes()).hexdigest(),
        "expected_plan_revision": state["revision"],
    }, tmp_path)
    plan_after_delete = (manuscript / "projection_plan.json").read_bytes()
    chapter.write_text("Inserted at the deleted boundary.\n" + chapter.read_text())

    with pytest.raises(ValueError, match="gap is modified or ambiguous"):
        structure.change("book", deleted["undo"], tmp_path)

    assert (manuscript / "projection_plan.json").read_bytes() == plan_after_delete
    assert chapter.read_text().startswith("Inserted at the deleted boundary.")


def test_restore_preserves_unrelated_plan_addition(tmp_path):
    manuscript, chapter, _plan = _section_fixture(tmp_path)
    from laplace.manuscript import project_structure, storyboard
    state = project_structure.state("book", tmp_path)
    deleted = structure.change("book", {
        "operation": "delete", "section_id": "first",
        "expected_source_digest": hashlib.sha256(chapter.read_bytes()).hexdigest(),
        "expected_plan_revision": state["revision"],
    }, tmp_path)
    added = storyboard.plan_write("book", {"kind": "add-section", "section": "extra",
        "title": "Extra", "outline_kind": "chapter", "parent_id": None}, tmp_path)
    assert added["applied"]

    structure.change("book", deleted["undo"], tmp_path)

    plan = json.loads((manuscript / "projection_plan.json").read_text())
    assert [row["id"] for row in plan["sections"]] == [
        "first", "first-child", "second", "extra"]


def test_restore_rejects_reused_plan_identity_and_rolls_source_back(tmp_path):
    manuscript, chapter, _plan = _section_fixture(tmp_path)
    from laplace.manuscript import project_structure, storyboard
    state = project_structure.state("book", tmp_path)
    deleted = structure.change("book", {
        "operation": "delete", "section_id": "first",
        "expected_source_digest": hashlib.sha256(chapter.read_bytes()).hexdigest(),
        "expected_plan_revision": state["revision"],
    }, tmp_path)
    source_after_delete = chapter.read_bytes()
    added = storyboard.plan_write("book", {"kind": "add-section", "section": "first",
        "title": "Conflicting reuse", "outline_kind": "chapter", "parent_id": None}, tmp_path)
    assert added["applied"]

    with pytest.raises(ValueError, match="identity was reused"):
        structure.change("book", deleted["undo"], tmp_path)

    assert chapter.read_bytes() == source_after_delete
    plan = json.loads((manuscript / "projection_plan.json").read_text())
    assert next(row for row in plan["sections"] if row["id"] == "first")["title"] == "Conflicting reuse"


def test_restore_gap_refuses_ambiguous_context():
    receipt = {"anchors": {"deleted": "REMOVED", "left": "LEFT", "right": "RIGHT"}}
    with pytest.raises(ValueError, match="ambiguous"):
        structure._restore_gap("LEFTRIGHT middle LEFTRIGHT", receipt)


def test_delete_rejects_stale_source_or_structure_revision(tmp_path):
    _manuscript, chapter, _plan = _section_fixture(tmp_path)
    from laplace.manuscript import project_structure
    state = project_structure.state("book", tmp_path)
    with pytest.raises(ValueError, match="source changed"):
        structure.change("book", {"operation": "delete", "section_id": "first",
            "expected_source_digest": "0" * 64,
            "expected_plan_revision": state["revision"]}, tmp_path)
    with pytest.raises(ValueError, match="projection plan changed"):
        structure.change("book", {"operation": "delete", "section_id": "first",
            "expected_source_digest": hashlib.sha256(chapter.read_bytes()).hexdigest(),
            "expected_plan_revision": "sha256:stale"}, tmp_path)


def test_source_only_nested_heading_deletes_without_initialising_plan(tmp_path):
    manuscript = _book(tmp_path)
    chapter = manuscript / "chapters" / "chapter-01.tex"
    original = "\\chapter{A \\emph{nested} title}\nBody.\n"
    chapter.write_text(original)
    from laplace.manuscript import project_structure
    state = project_structure.state("book", tmp_path)
    assert state["status"] == "MISSING"

    deleted = structure.change("book", {
        "operation": "delete", "section_id": "chapter-01",
        "source_file": "chapters/chapter-01.tex", "line_start": 1,
        "expected_source_digest": hashlib.sha256(chapter.read_bytes()).hexdigest(),
        "expected_plan_revision": state["revision"],
    }, tmp_path)

    assert chapter.read_text() == ""
    assert json.loads((manuscript / "projection_plan.json").read_text())["sections"] == []
    inverse = structure.undo_record("book", deleted["undo_ref"]["id"], tmp_path)
    restored = structure.change("book", inverse["undo"], tmp_path)
    assert chapter.read_text() == original
    structure.change("book", structure.undo_record("book", restored["undo_ref"]["id"], tmp_path)["undo"], tmp_path)
    assert chapter.read_text() == ""
    assert json.loads((manuscript / "projection_plan.json").read_text())["sections"] == []


def test_last_root_section_span_preserves_document_tail_and_ignores_commented_heading():
    text = ("% \\section{Decoy}\n\\begin{document}\n\\chapter{Writing integration}\n"
            "Opening paragraph.\n\\section{Worked example}\nExample body.\n"
            "A final paragraph remains part of the section.\n"
            "\\begin{thebibliography}{9}\n\\bibitem{x} Reference.\n"
            "\\end{thebibliography}\n\\end{document}\n")
    start, end = structure._source_span(text, line_start=5)
    updated = text[:start] + text[end:]
    assert "\\chapter{Writing integration}" in updated and "Opening paragraph." in updated
    assert "\\section{Worked example}" not in updated and "Example body." not in updated
    assert "A final paragraph remains part of the section." not in updated
    assert "\\begin{thebibliography}{9}" in updated
    assert "\\bibitem{x} Reference." in updated and "\\end{document}" in updated


def test_create_nested_section_coemits_plan_and_delete_undo_recovers_source(tmp_path):
    manuscript, chapter, _ = _section_fixture(tmp_path)
    from laplace.manuscript import project_structure
    before = chapter.read_text()
    state = project_structure.state("book", tmp_path)
    created = structure.change("book", {"operation": "create", "source_file": "chapters/chapter-01.tex",
        "after_line": 4, "after_before": "Child body.", "expected_source_digest": hashlib.sha256(chapter.read_bytes()).hexdigest(),
        "expected_plan_revision": state["revision"], "title": "Nested new", "kind": "subsection",
        "parent_id": "first-child", "section_id": "nested-new"}, tmp_path)
    assert "\\subsection{Nested new}" in chapter.read_text()
    plan = json.loads((manuscript / "projection_plan.json").read_text())
    new = next(row for row in plan["sections"] if row["id"] == "nested-new")
    assert new["parent_id"] == "first-child" and new["nodes_in_order"] == []
    assert created["edits"][0]["before"] == before
    assert created['undo']['operation']=='undo-create'
    undone=structure.change("book", created["undo"], tmp_path)
    assert chapter.read_text() == before
    assert "nested-new" not in {row["id"] for row in json.loads((manuscript / "projection_plan.json").read_text())["sections"]}
    redone=structure.change('book',undone['undo'],tmp_path)
    assert '\\subsection{Nested new}' in chapter.read_text()
    structure.change('book',redone['undo'],tmp_path)
    assert chapter.read_text()==before


def test_heading_create_undo_preserves_existing_trailing_prose_and_unrelated_edit(tmp_path):
    manuscript,chapter,_=_section_fixture(tmp_path)
    from laplace.manuscript import project_structure
    before=chapter.read_text();lines=before.split('\n')
    created=structure.change('book',{'operation':'create','source_file':'chapters/chapter-01.tex',
        'after_line':1,'after_before':lines[0],'expected_source_digest':hashlib.sha256(chapter.read_bytes()).hexdigest(),
        'expected_plan_revision':project_structure.state('book',tmp_path)['revision'],
        'title':'Inserted before existing prose','kind':'section'},tmp_path)
    chapter.write_text(chapter.read_text().replace('Child body.','Author revised child body.'))
    structure.change('book',created['undo'],tmp_path)
    assert chapter.read_text()==before.replace('Child body.','Author revised child body.')


def test_create_refuses_stale_boundary_without_writing(tmp_path):
    _manuscript, chapter, _ = _section_fixture(tmp_path)
    before = chapter.read_bytes()
    from laplace.manuscript import project_structure
    state = project_structure.state("book", tmp_path)
    with pytest.raises(ValueError, match="after_before"):
        structure.change("book", {"operation": "create", "source_file": "chapters/chapter-01.tex",
            "after_line": 2, "after_before": "Wrong.", "expected_source_digest": hashlib.sha256(before).hexdigest(),
            "expected_plan_revision": state["revision"], "title": "No write", "kind": "section"}, tmp_path)
    assert chapter.read_bytes() == before


def test_create_source_only_heading_needs_no_projection_plan(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    (source / "main.tex").write_text("\\documentclass{article}\n\\begin{document}\nBody.\n\\end{document}\n")
    status, row = writing_projects.import_source({"name": "plain", "title": "Plain", "root": "source/main.tex", "editable": True}, tmp_path)
    assert status == 201, row
    main = source / "main.tex"
    created = structure.change("plain", {"operation": "create", "source_file": "main.tex", "after_line": 3,
        "after_before": "Body.", "expected_source_digest": hashlib.sha256(main.read_bytes()).hexdigest(),
        "title": "Inserted", "kind": "section", "section_id": "inserted"}, tmp_path)
    assert "\\section{Inserted}" in main.read_text() and created["receipt"]["section_id"] == "inserted"


def test_convert_rich_paragraph_preserves_tex_plan_position_and_inverse(tmp_path):
    manuscript, chapter, _ = _section_fixture(tmp_path)
    from laplace.manuscript import project_structure
    rich = r"A \emph{useful} bound $x^2$."
    chapter.write_text(chapter.read_text().replace('First body.', rich))
    before = chapter.read_text()
    created = structure.change('book', {'operation':'convert', 'source_file':'chapters/chapter-01.tex',
        'replacement':{'line_start':2,'line_end':2,'before':rich},
        'expected_source_digest':hashlib.sha256(chapter.read_bytes()).hexdigest(),
        'expected_plan_revision':project_structure.state('book',tmp_path)['revision'],
        'title':'A useful bound x squared', 'kind':'section', 'parent_id':'first', 'section_id':'bound'}, tmp_path)
    after = chapter.read_text()
    assert r'\section{' + rich + '}' in after
    plan = json.loads((manuscript/'projection_plan.json').read_text())
    assert [row['id'] for row in plan['sections']] == ['first','bound','first-child','second']
    entry = next(row for row in plan['sections'] if row['id']=='bound')
    assert entry['source_file']=='chapters/chapter-01.tex'
    assert entry['source_label']=='section:bound' and entry['source_title']==rich
    assert created['correction_id']
    undone = structure.change('book',created['undo'],tmp_path)
    assert chapter.read_text()==before
    assert undone['undo']['replacement']['before']==rich
    redone = structure.change('book',undone['undo'],tmp_path)
    assert chapter.read_text()==after
    assert [row['id'] for row in json.loads((manuscript/'projection_plan.json').read_text())['sections']] == ['first','bound','first-child','second']
    structure.change('book',redone['undo'],tmp_path)
    assert chapter.read_text()==before


def test_conversion_refuses_partial_or_stale_paragraph_without_source_or_plan_write(tmp_path):
    manuscript,chapter,_=_section_fixture(tmp_path)
    from laplace.manuscript import project_structure
    source,plan=chapter.read_bytes(),(manuscript/'projection_plan.json').read_bytes()
    payload={'operation':'convert','source_file':'chapters/chapter-01.tex',
        'replacement':{'line_start':2,'line_end':2,'before':'Old body.'},
        'expected_source_digest':hashlib.sha256(source).hexdigest(),
        'expected_plan_revision':project_structure.state('book',tmp_path)['revision'],
        'title':'Refused','kind':'section','parent_id':'first'}
    with pytest.raises(ValueError,match='paragraph changed'):structure.change('book',payload,tmp_path)
    payload['replacement']={'line_start':1,'line_end':1,'before':r'\chapter{First}'}
    with pytest.raises(ValueError,match='whole prose paragraph'):structure.change('book',payload,tmp_path)
    assert chapter.read_bytes()==source and (manuscript/'projection_plan.json').read_bytes()==plan


def test_heading_rename_and_source_undo_follow_plan_but_keep_independent_plan_title(tmp_path,monkeypatch):
    manuscript,chapter,_=_section_fixture(tmp_path)
    from laplace.manuscript import review_surface
    monkeypatch.setattr(review_surface,'_repo_root',lambda:tmp_path)
    def rename(before,after):
        result=review_surface.adjudicate(manuscript,'book',{'verb':'rewrite','by':'author','expected_selection':source_owner.observation('book',tmp_path)['selection_identity'],
            'file':'chapters/chapter-01.tex','line_start':1,'line_end':1,'before':before,'after':after})
        assert result.get('ok') and result.get('applied'),result
        return json.loads((manuscript/'projection_plan.json').read_text())['sections'][0]
    assert rename(r'\chapter{First}',r'\chapter{Renamed first}')['title']=='Renamed first'
    assert rename(r'\chapter{Renamed first}',r'\chapter{First}')['title']=='First'
    from laplace.manuscript import storyboard
    assert storyboard.plan_write('book',{'kind':'retitle','section':'first','title':'Independent reader framing'},tmp_path)['applied']
    assert rename(r'\chapter{First}',r'\chapter{Different source heading}')['title']=='Independent reader framing'


def test_converted_rich_heading_source_rename_follows_its_label(tmp_path,monkeypatch):
    manuscript,chapter,_=_section_fixture(tmp_path)
    from laplace.manuscript import project_structure, review_surface
    monkeypatch.setattr(review_surface,'_repo_root',lambda:tmp_path)
    rich=r'An \emph{exact} bound $x^2$'
    chapter.write_text(chapter.read_text().replace('First body.',rich))
    structure.change('book',{'operation':'convert','source_file':'chapters/chapter-01.tex',
        'replacement':{'line_start':2,'line_end':2,'before':rich},'title':'An exact bound','kind':'section',
        'parent_id':'first','section_id':'bound','expected_source_digest':hashlib.sha256(chapter.read_bytes()).hexdigest(),
        'expected_plan_revision':project_structure.state('book',tmp_path)['revision']},tmp_path)
    before=r'\section{'+rich+'}';after=r'\section{A \emph{revised} bound $x^2$}'
    result=review_surface.adjudicate(manuscript,'book',{'verb':'rewrite','by':'author','expected_selection':source_owner.observation('book',tmp_path)['selection_identity'],'file':'chapters/chapter-01.tex',
        'line_start':2,'line_end':2,'before':before,'after':after})
    assert result.get('applied'),result
    entry=next(row for row in json.loads((manuscript/'projection_plan.json').read_text())['sections'] if row['id']=='bound')
    assert entry['title']==r'A \emph{revised} bound $x^2$'
    assert entry['source_label']=='section:bound'


def test_rich_conversion_rename_undo_rename_then_undo_conversion(tmp_path,monkeypatch):
    manuscript,chapter,_=_section_fixture(tmp_path)
    from laplace.manuscript import project_structure, review_surface
    monkeypatch.setattr(review_surface,'_repo_root',lambda:tmp_path)
    rich=r'A \emph{useful} bound $x^2$'
    chapter.write_text(chapter.read_text().replace('First body.',rich));original=chapter.read_text()
    created=structure.change('book',{'operation':'convert','source_file':'chapters/chapter-01.tex',
        'replacement':{'line_start':2,'line_end':2,'before':rich},'title':'A useful bound x squared',
        'kind':'section','parent_id':'first','section_id':'bound',
        'expected_source_digest':hashlib.sha256(chapter.read_bytes()).hexdigest(),
        'expected_plan_revision':project_structure.state('book',tmp_path)['revision']},tmp_path)
    before=r'\section{'+rich+'}';after=r'\section{A renamed bound}'
    for left,right in [(before,after),(after,before)]:
        result=review_surface.adjudicate(manuscript,'book',{'verb':'rewrite','by':'author','expected_selection':source_owner.observation('book',tmp_path)['selection_identity'],
            'file':'chapters/chapter-01.tex','line_start':2,'line_end':2,'before':left,'after':right})
        assert result.get('applied'),result
    entry=next(row for row in json.loads((manuscript/'projection_plan.json').read_text())['sections'] if row['id']=='bound')
    assert entry['title']=='A useful bound x squared'
    undone=structure.change('book',created['undo'],tmp_path)
    assert chapter.read_text()==original and undone['undo']['operation']=='convert'


def test_heading_included_file_inserts_before_root_afterword(tmp_path):
    manuscript,chapter,plan=_section_fixture(tmp_path)
    from laplace.manuscript import project_structure
    main=manuscript/'Fixture-Book.tex'
    main.write_text('\\documentclass{book}\n\\begin{document}\n\\chapter{Preface}\\label{ch:preface}\n\\input{chapters/chapter-01}\\chapter{Afterword}\\label{ch:afterword}\nAfterword body.\n\\end{document}\n')
    base={'kind':'chapter','parent_id':None,'job':'','notes':'','refs':[],'beats':[],'nodes_in_order':[],'figures':[],'source_file':'Fixture-Book.tex'}
    plan['sections']=[{**base,'id':'preface','title':'Preface','source_label':'ch:preface'},*plan['sections'],{**base,'id':'afterword','title':'Afterword','source_label':'ch:afterword'}]
    (manuscript/'projection_plan.json').write_text(json.dumps(plan))
    lines=chapter.read_text().split('\n')
    structure.change('book',{'operation':'create','source_file':'chapters/chapter-01.tex','after_line':6,
        'after_before':lines[5],'title':'Last included section','kind':'section','parent_id':'second','section_id':'last-included',
        'expected_source_digest':hashlib.sha256(chapter.read_bytes()).hexdigest(),
        'expected_plan_revision':project_structure.state('book',tmp_path)['revision']},tmp_path)
    assert [row['id'] for row in json.loads((manuscript/'projection_plan.json').read_text())['sections']]==['preface','first','first-child','second','last-included','afterword']


def test_label_correspondence_handles_nested_title_and_independent_plan_wording():
    from laplace.manuscript.project_structure import _source_correspondence
    title=r'A \emph{nested} title $x^2$'
    row=_source_correspondence({'root':'book.tex','manuscript_dir':'manuscript'},{'sources':[{'file':'manuscript/one.tex','text':r'\section{'+title+'}\\label{sec:one}\nBody.'}]},
        {'id':'one','title':'Readable title','source_file':'one.tex','source_label':'sec:one','source_title':title,'source_plan_title':'Readable title'})
    assert row['status']=='MATCHED' and row['title_status']=='MATCHED'
    assert row['heading']['title']==title and row['source_label']=='sec:one'


def test_conversion_cannot_be_silently_interpreted_as_insertion(tmp_path):
    manuscript,chapter,_=_section_fixture(tmp_path)
    before=chapter.read_bytes()
    with pytest.raises(ValueError,match='operation convert'):
        structure.change('book',{'operation':'create','replacement':{'line_start':2,'line_end':2,'before':'First body.'}},tmp_path)
    assert chapter.read_bytes()==before


def test_compact_heading_inverse_and_exact_source_plan_receipts(tmp_path):
    manuscript,chapter,_=_section_fixture(tmp_path)
    from laplace.manuscript import project_structure
    original=chapter.read_text();state=project_structure.state('book',tmp_path)
    result=structure.change('book',{'operation':'convert','source_file':'chapters/chapter-01.tex',
        'replacement':{'line_start':2,'line_end':2,'before':'First body.'},'title':'New heading',
        'kind':'section','parent_id':'first','section_id':'converted',
        'expected_source_digest':hashlib.sha256(chapter.read_bytes()).hexdigest(),
        'expected_plan_revision':state['revision']},tmp_path)
    rows=result['owned_changes']['files']
    assert {Path(row['path']).name for row in rows}=={'chapter-01.tex','projection_plan.json'}
    assert all(row['after_sha256']==row['observed_after_sha256'] for row in rows)
    assert structure.undo_record('book',result['undo_ref']['id'],tmp_path)['undo']==result['undo']
    restored=structure.change('book',result['undo'],tmp_path)
    assert chapter.read_text()==original
    redone=structure.change('book',structure.undo_record('book',restored['undo_ref']['id'],tmp_path)['undo'],tmp_path)
    assert redone['operation']=='convert' and '\\section{First body.}' in chapter.read_text()


def test_structure_help_variants_and_examples_use_the_exact_owner_contract():
    from laplace.manuscript import project_structure
    from laplace.native import declarations as writing_declarations
    from jsonschema import validate
    # Every variant is built from the owner's contract, and the GENERATED example for each
    # one satisfies the owner's own validator -- which the five hand-written examples this
    # replaces could not be relied on to do, since two of them named objects no project has.
    owner=project_structure.operation_contract()['operations']
    variants=writing_declarations.variants('structure_change')
    assert set(variants)==set(owner)
    for name,variant in variants.items():
        required = set(owner[name]['required'])
        legacy = {field for route in writing_declarations._variant_routes('structure_change', name)
                  for field, _homes, form, optional in route.guards
                  if form == 'digest' and not optional and field in required}
        assert set(variant['required']) == required - legacy
        if legacy:
            alternatives=variant['allOf'][-1]['anyOf']
            assert alternatives[0] == {'required':['expected'], 'properties':{'expected':{'minItems':1}}}
            assert set(alternatives[1]['required']) == legacy  # JSON Schema required order has no meaning.
        else:
            assert variant.get('allOf') == owner[name].get('allOf')
        assert variant['properties']['operation']=={'const':name}
        example = writing_declarations.generated_example('structure_change',variant=name)
        project_structure._validate_change_payload(example)
        validate(example, variant)
        if legacy:
            # Both existing guard routes remain admitted; neither admits absence.
            canonical = {key:value for key,value in example.items() if key not in legacy}
            canonical['expected'] = ['source-file@book::main.tex#sha256:' + '0'*64]
            validate(canonical, variant)
            missing = {key:value for key,value in canonical.items() if key != 'expected'}
            from jsonschema import ValidationError
            with pytest.raises(ValidationError):
                validate(missing, variant)


def test_convert_root_paragraph_uses_reader_content_mask_and_keeps_document_wrapper(tmp_path):
    manuscript=_book(tmp_path);main=manuscript/'Fixture-Book.tex'
    paragraph=r'A root \emph{paragraph}.'
    original=main.read_text().replace('\\end{document}',paragraph+'\n\\end{document}');main.write_text(original)
    line=original.split('\n').index(paragraph)+1
    state=structure._structure_state('book',tmp_path)
    changed=structure.change('book',{'operation':'convert','source_file':'Fixture-Book.tex',
        'replacement':{'line_start':line,'line_end':line,'before':paragraph},'kind':'section',
        'title':'Root paragraph','section_id':'root-paragraph','expected_source_digest':hashlib.sha256(main.read_bytes()).hexdigest(),
        'expected_plan_revision':state['revision']},tmp_path)
    assert '\\section{'+paragraph+'}' in main.read_text()
    structure.change('book',changed['undo'],tmp_path);assert main.read_text()==original


@pytest.mark.parametrize("planned", [False, True])
def test_subsection_delete_and_restore_preserve_parent_and_equal_level_sibling(tmp_path, planned):
    manuscript, chapter, plan = _section_fixture(tmp_path)
    from laplace.manuscript import project_structure
    prefix = "\\chapter{First}\n\\section{First child}\nParent body.\n"
    removed = "\\subsection{Inner}\n\\label{sub:inner}\nInner body.\n\\subsubsection{Detail}\nNested body.\n"
    suffix = "\\subsection{Sibling}\nSibling body.\n\\chapter{Second}\nSecond body.\n"
    chapter.write_text(prefix + removed + suffix)
    if planned:
        plan['sections'].insert(2, {'id':'inner-plan','title':'Inner','kind':'subsection',
            'parent_id':'first-child','source_file':'chapters/chapter-01.tex','source_label':'sub:inner',
            'job':'bounded subsection','nodes_in_order':[],'refs':[],'beats':[],'figures':[]})
        (manuscript / 'projection_plan.json').write_text(json.dumps(plan))
    original_plan = json.loads((manuscript / 'projection_plan.json').read_text())
    state = project_structure.state('book', tmp_path)
    removed_result = structure.change('book', {'operation':'delete',
        'section_id':'inner-plan' if planned else 'sub:inner',
        'source_file':chapter.relative_to(tmp_path).as_posix(), 'line_start':4, 'kind':'subsection',
        'expected_source_digest':hashlib.sha256(chapter.read_bytes()).hexdigest(),
        'expected_plan_revision':state['revision']}, tmp_path)
    assert chapter.read_text() == prefix + suffix
    remaining = json.loads((manuscript / 'projection_plan.json').read_text())
    assert [row['id'] for row in remaining['sections']] == ['first','first-child','second']
    restored = structure.change('book', removed_result['undo'], tmp_path)
    assert restored['ok'] and chapter.read_text() == prefix + removed + suffix
    assert json.loads((manuscript / 'projection_plan.json').read_text()) == original_plan
