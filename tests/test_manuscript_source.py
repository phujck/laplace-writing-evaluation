import json
from pathlib import Path

from laplace.manuscript import manuscript_source
from laplace.pipeline import document_model


def _project(root: Path, manifest: dict | None = None, tex_root: str | None = None) -> None:
    base = root / "synthetics papers" / "book" / "manuscript"
    base.mkdir(parents=True)
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "book", "tex_root": tex_root or "synthetics papers/book/manuscript",
        "manifest": manifest or {},
    }]}), encoding="utf-8")


def test_explicit_edition_and_nested_traversal_keep_source_order_and_spans(tmp_path):
    _project(tmp_path, {"document": {"edition": "book-v2", "root": "book.tex"}})
    md = tmp_path / "synthetics papers" / "book" / "manuscript"
    (md / "book.tex").write_text(
        "\\documentclass{book}\n\\begin{document}\n\\input{front}\n"
        "\\include{chapters/one}\n\\end{document}\n", encoding="utf-8")
    (md / "front.tex").write_text("\\part{Start}\nFront words.\n", encoding="utf-8")
    (md / "chapters").mkdir()
    # TeX resolves \\input against the compilation directory (the root's), not the including file's: the nested
    # file is named root-relative, as the build reads it (WORK-editor-tex-include-resolution-20261016; the
    # including-relative spelling is reported missing with its alternate, tests/test_tex_include_resolution.py)
    (md / "chapters" / "one.tex").write_text("\\chapter{One}\n\\input{chapters/nested/two}\n", encoding="utf-8")
    (md / "chapters" / "nested").mkdir()
    (md / "chapters" / "nested" / "two.tex").write_text("Nested text.\n", encoding="utf-8")

    source = manuscript_source.resolve("book", repo_root=tmp_path)
    assert source["status"] == "resolved"
    assert source["edition"] == "book-v2"
    tree = manuscript_source.traversal(source["root"], repo_root=tmp_path)
    assert [row["file"] for row in tree["sources"]] == [
        "synthetics papers/book/manuscript/book.tex",
        "synthetics papers/book/manuscript/front.tex",
        "synthetics papers/book/manuscript/chapters/one.tex",
        "synthetics papers/book/manuscript/chapters/nested/two.tex",
    ]
    assert tree["sources"][2]["include_line"] == 4
    assert tree["sources"][3]["include_line"] == 2
    assert tree["sources"][3]["parent"].endswith("chapters/one.tex")
    assert tree["sources"][3]["byte_end"] == len("Nested text.\n".encode())


def test_source_observation_tracks_included_changes_not_unrelated_projects(tmp_path,monkeypatch):
    _project(tmp_path,{'document':{'root':'main.tex'}})
    md=tmp_path/'synthetics papers/book/manuscript'
    (md/'main.tex').write_text('\\documentclass{book}\n\\begin{document}\n\\input{chapter}\n\\input{chapter}\n\\end{document}\n')
    (md/'chapter.tex').write_text('\\chapter{One}\nOriginal included prose.\n')
    source=manuscript_source.resolve('book',repo_root=tmp_path)
    reads=[];original=Path.read_bytes
    def observed(path):reads.append(path);return original(path)
    monkeypatch.setattr(Path,'read_bytes',observed)
    tree=manuscript_source.traversal(source['root'],tmp_path)
    assert reads.count(md/'chapter.tex')==1
    first=manuscript_source.observation('book',tmp_path,source=source,source_tree=tree)
    assert first['file_revisions'].keys()=={str(p.relative_to(tmp_path)) for p in (md/'main.tex',md/'chapter.tex')}
    (tmp_path/'unrelated.tex').write_text('Unrelated project.')
    assert manuscript_source.observation('book',tmp_path,source=source)['revision']==first['revision']
    (md/'chapter.tex').write_text('\\chapter{Two}\nChanged included prose.\n')
    second=manuscript_source.observation('book',tmp_path,source=source)
    assert second['selected_source']==first['selected_source']
    assert second['source_revision']!=first['source_revision'] and second['revision']!=first['revision']


def test_empty_scaffold_can_use_the_only_substantive_registered_candidate(tmp_path):
    _project(tmp_path)
    md = tmp_path / "synthetics papers" / "book" / "manuscript"
    (md / "main.tex").write_text("\\documentclass{article}\n\\begin{document}\n\\end{document}\n")
    (md / "edition.tex").write_text("\\documentclass{article}\n\\begin{document}\nA real manuscript body.\n\\end{document}\n")

    source = manuscript_source.resolve("book", repo_root=tmp_path)
    assert source["status"] == "resolved"
    assert source["root"].endswith("edition.tex")
    assert "empty registered main.tex" in source["diagnostics"][0]


def test_multiple_substantive_candidates_require_manifest_selection(tmp_path):
    _project(tmp_path)
    md = tmp_path / "synthetics papers" / "book" / "manuscript"
    for name in ("one.tex", "two.tex"):
        (md / name).write_text("\\documentclass{article}\n\\begin{document}\nA complete alternative.\n\\end{document}\n")

    source = manuscript_source.resolve("book", repo_root=tmp_path)
    assert source["status"] == "ambiguous"
    assert source["root"] is None


def test_document_model_uses_selected_book_and_part_chapter_headings(tmp_path):
    _project(tmp_path, {"document": {"root": "book.tex"}})
    md = tmp_path / "synthetics papers" / "book" / "manuscript"
    (md / "book.tex").write_text("\\documentclass{book}\n\\input{chapter}\n")
    (md / "chapter.tex").write_text("\\part{Part I}\n\\chapter{A chapter}\nText enough for a prose block here.\n")

    model = document_model.build_document_model("book", repo_root=tmp_path, write=False)
    assert model["main"].endswith("book.tex")
    assert model["input_order"][-1].endswith("chapter.tex")
    assert model["sections"][1]["headings"] == ["Part I", "A chapter"]


def test_saved_selection_is_explicit_and_revision_guarded(tmp_path):
    _project(tmp_path)
    md = tmp_path / "synthetics papers" / "book" / "manuscript"
    for name in ("one.tex", "two.tex"):
        (md / name).write_text("\\documentclass{article}\n\\begin{document}\nA real edition.\n\\end{document}\n")
    before = manuscript_source.resolve("book", repo_root=tmp_path)
    assert before["status"] == "ambiguous"
    selected = manuscript_source.select("book", "synthetics papers/book/manuscript/two.tex",
                                        repo_root=tmp_path)
    assert selected["selection"] == "saved"
    assert selected["root"].endswith("two.tex")
    try:
        manuscript_source.select("book", "synthetics papers/book/manuscript/one.tex",
                                 repo_root=tmp_path, expected_revision="stale")
    except ValueError as exc:
        assert "changed" in str(exc)
    else:
        raise AssertionError("selection accepted a stale revision")


def test_walk_uses_registered_source_when_target_is_an_empty_scaffold(tmp_path, monkeypatch):
    from laplace.manuscript import review_surface, walk

    _project(tmp_path)
    md = tmp_path / "synthetics papers" / "book" / "manuscript"
    (md / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n\\section{Live}\nA readable body.\n\\end{document}\n")
    target = md / "whitepaper"
    target.mkdir()
    (target / "main.tex").write_text("\\documentclass{article}\n\\begin{document}\n\\end{document}\n")
    monkeypatch.setattr(walk, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(review_surface, "manuscript_dir", lambda *_args: target)

    rendered = walk.doc("book")
    assert rendered["ok"] is True
    assert rendered["root"].endswith("manuscript/main.tex")
    assert rendered["counts"]["blocks"] > 0


def test_walk_reports_empty_registered_source_without_false_success(tmp_path, monkeypatch):
    from laplace.manuscript import review_surface, walk

    _project(tmp_path, tex_root="synthetics papers/book/manuscript/tex")
    md = tmp_path / "synthetics papers" / "book" / "manuscript"
    tex = md / "tex"
    tex.mkdir()
    (tex / "main.tex").write_text("\\documentclass{article}\n\\begin{document}\n\\maketitle\n\\end{document}\n")
    monkeypatch.setattr(walk, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(review_surface, "manuscript_dir", lambda *_args: md)

    rendered = walk.doc("book")
    assert rendered["ok"] is False
    assert rendered["status"] == "empty-source"
    assert rendered["source_status"] == "empty"
