from __future__ import annotations

import json
from pathlib import Path

from laplace.manuscript import review_surface, walk


def _fixture(root: Path, monkeypatch):
    manuscript = root / "book/manuscript"
    manuscript.mkdir(parents=True)
    main = manuscript / "main.tex"
    main.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{graphicx}\n\\begin{document}\n\\section{Figures}\n"
        "\\begin{figure}\n\\centering\n\\rule{1cm}{1cm}\n"
        "\\caption{A \\textbf{bold} caption with $x$.}\\label{fig:one}\n"
        "\\end{figure}\n\n"
        "\\begin{figure}\n\\centering\n\\rule{1cm}{1cm}\n"
        "\\caption{A multiline caption with \\emph{emphasis},\n"
        "and a \\Cref{fig:one} on its second line.}\n"
        "\\label{fig:two}\n\\end{figure}\n\\end{document}\n",
        encoding="utf-8")
    root.joinpath("registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "book", "project_dir": "book", "tex_root": "book/manuscript",
        "manifest": {"document": {"root": "book/manuscript/main.tex"}},
    }]}))
    monkeypatch.setattr(walk, "_repo_root", lambda: root)
    monkeypatch.setattr(review_surface, "_repo_root", lambda: root)
    return manuscript, main


def _caption_blocks(document):
    return [block for section in document["sections"] for block in section["blocks"]
            if block["kind"] == "caption"]


def _rewrite(manuscript: Path, block: dict, old: str, new: str):
    assert old in block["tex"]
    after = block["tex"].replace(old, new, 1)
    return review_surface.adjudicate(manuscript, "book", {
        "verb": "rewrite", "by": "author", "file": block["src"]["file"],
        "line_start": block["src"]["line_start"], "line_end": block["src"]["line_end"],
        "before": block["tex"], "after": after, "scope": "sentence",
        "note": "Caption-only fixture edit",
    })


def test_caption_blocks_have_exact_commands_piece_offsets_and_no_duplicate_figure_caption(tmp_path, monkeypatch):
    _manuscript, main = _fixture(tmp_path, monkeypatch)
    document = walk.doc("book")
    captions = _caption_blocks(document)
    figures = [block for section in document["sections"] for block in section["blocks"]
               if block["kind"] == "figure"]

    assert len(captions) == len(figures) == 2
    assert all(figure["caption_separate"] is True for figure in figures)
    assert [caption["caption_of"] for caption in captions] == [figure["id"] for figure in figures]
    assert captions[0]["src"]["line_start"] == captions[0]["src"]["line_end"] == 8
    assert captions[0]["tex"].endswith(r"\label{fig:one}")
    assert captions[1]["src"]["line_start"] == 14
    assert captions[1]["src"]["line_end"] == 15
    assert captions[1]["tex"].startswith(r"\caption{A multiline")
    assert r"\label{fig:two}" not in captions[1]["tex"]
    assert walk._flatten_pieces(captions[0]["pieces"]) == "A bold caption with $x$."
    assert walk._flatten_pieces(captions[1]["pieces"]) == (
        "A multiline caption with emphasis, and a fig:one on its second line.")
    for caption in captions:
        assert all(0 <= piece["o_start"] <= piece["o_end"] <= len(caption["tex"])
                   for piece in caption["pieces"])
        assert "".join(main.read_text().splitlines(keepends=True)[
            caption["src"]["line_start"] - 1:caption["src"]["line_end"]]).rstrip("\n") == caption["tex"]


def test_caption_only_rewrites_preserve_figure_source_macros_and_labels_and_refuse_stale_before(tmp_path, monkeypatch):
    manuscript, main = _fixture(tmp_path, monkeypatch)
    before_file = main.read_text()
    first, second = _caption_blocks(walk.doc("book"))

    applied = _rewrite(manuscript, first, "caption with", "caption retaining")
    assert applied.get("ok") and not applied.get("pending")
    after_first = main.read_text()
    assert after_first == before_file.replace("caption with", "caption retaining", 1)
    assert r"\textbf{bold}" in after_first and r"\label{fig:one}" in after_first
    assert r"\rule{1cm}{1cm}" in after_first

    stale = _rewrite(manuscript, first, "caption with", "caption overwritten")
    assert stale.get("pending") or stale.get("error")
    assert main.read_text() == after_first

    # Re-read after the first edit so the multiline caption carries current line bytes.
    second = _caption_blocks(walk.doc("book"))[1]
    applied = _rewrite(manuscript, second, "its second line", "the second line")
    assert applied.get("ok") and not applied.get("pending")
    final = main.read_text()
    assert "the second line" in final
    assert r"\emph{emphasis}" in final and r"\Cref{fig:one}" in final
    assert final.count(r"\label{fig:one}") == 1 and final.count(r"\label{fig:two}") == 1
    assert final.count(r"\begin{figure}") == 2 and final.count(r"\end{figure}") == 2


def test_unbalanced_caption_never_becomes_a_partial_edit_surface():
    text = ("\\begin{figure}\n\\centering\n\\rule{1cm}{1cm}\n"
            "\\caption{Broken caption\n\\label{fig:broken}\n\\end{figure}\n")
    blocks = walk.blocks_for(text, file_rel="broken.tex", repo_file="broken.tex",
                             md=Path("."), corpus="", dir_param="", para_spans=[],
                             known_macros={})

    assert len(blocks) == 1 and blocks[0]["kind"] == "figure"
    assert blocks[0]["tex"] == text.rstrip("\n")
    assert blocks[0]["caption"] == "" and not blocks[0].get("caption_separate")
    assert not any(block["kind"] == "caption" for block in blocks)
