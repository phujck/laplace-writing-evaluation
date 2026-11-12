from pathlib import Path

from laplace.manuscript.walk import blocks_for


def _blocks(text: str):
    return blocks_for(text, file_rel="chapter.tex", repo_file="chapter.tex", md=Path("/tmp"),
                      corpus="", dir_param="", para_spans=[], known_macros=frozenset())


def test_explicit_par_is_an_exact_editable_empty_paragraph_block():
    rows = _blocks("First.\n\n\\par\n")

    assert [(row["kind"], row["tex"], row["src"]["line_start"]) for row in rows] == [
        ("para", "First.", 1), ("para", r"\par", 3)]
    assert rows[1]["pieces"] == [{"t": "break", "o_start": 0, "o_end": 4}]


def test_explicit_par_before_prose_keeps_both_paragraphs_addressable():
    rows = _blocks("\\par\n\nSecond.\n")

    assert [(row["tex"], row["src"]["line_start"], row["src"]["line_end"]) for row in rows] == [
        (r"\par", 1, 1), ("Second.", 3, 3)]
