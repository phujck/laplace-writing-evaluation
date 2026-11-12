"""The author's own edit from the Writing editor is authoritative (wave 14a, his rulings 1 and 5).

An edit the walk sends as the author's typing (`surface: "walk"`, `source: "click-type"`) is applied
over the span as it is now, even when the text it was typed against has moved, and the bytes it
replaces are kept in the applied row's anchor as `superseded`. Every other writer --- an agent, a
proposal application, a rollback --- keeps the identity gate: a stale base banks a pending row or
is refused, and the file is not written.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from laplace.core import grammar as g
from laplace.manuscript import review_surface as rv
from laplace.pipeline.ledger import read_jsonl

pytestmark = pytest.mark.unit

_MAIN = "\\documentclass{article}\n\\begin{document}\n\\input{N1}\n\\end{document}\n"
_N1 = ("% PLAN:N1\n\\section{Introduction}\\label{sec:N1}\n\n% N1-p1\n"
       "The quick brown fox jumps over the lazy dog.\n\n% N1-p2\n"
       "The lazy dog sleeps here in the afternoon sun.\n")
_SPAN = (5, 5)
_TEXT = "The quick brown fox jumps over the lazy dog."


def _md(tmp_path: Path) -> Path:
    md = tmp_path / "ms"
    md.mkdir(parents=True)
    (md / "main.tex").write_text(_MAIN, encoding="utf-8")
    (md / "N1.tex").write_text(_N1, encoding="utf-8")
    (md / "feedback").mkdir()
    return md


def _token(text: str, span=_SPAN) -> str:
    return str(g.mint("prose", "proj::N1.tex:%d-%d" % span, g.digest_bytes(text.encode("utf-8"))))


def _write(md: Path, *, editor: bool, before=_TEXT, after=None, span=_SPAN, **extra) -> dict:
    payload = {"verb": "rewrite", "by": "author" if editor else "agent-standin", "corpus": "proj",
               "section": "N1", "file": "N1.tex", "line_start": span[0], "line_end": span[1],
               "before": before, "after": after if after is not None else before + " My newest sentence.",
               "passage_before": before, "passage_after": (after if after is not None else before + " My newest sentence.")}
    if editor:
        payload.update({"surface": "walk", "source": "click-type"})
    payload.update(extra)
    return rv.adjudicate(md, "proj", payload, repo_root=md.parent)


def _rows(md: Path) -> list[dict]:
    return read_jsonl(md / "feedback" / "feedback.jsonl")


def _line(md: Path, n: int) -> str:
    return (md / "N1.tex").read_text(encoding="utf-8").split("\n")[n - 1]


def test_the_authors_edit_over_his_own_earlier_save_applies_with_no_refusal(tmp_path):
    """The 9 November fault: the editor's own earlier save of his typing moved the span, his next
    save still carried the older text and token, and the door refused it as `state-not-reached`."""
    md = _md(tmp_path)
    first = _TEXT + " It occurs to me"
    assert _write(md, editor=True, after=first)["ok"]
    # his newest text, still typed against the text he started from, with that text's token
    newest = _TEXT + " It occurs to me that my perspective on life has been forcibly widened."
    res = _write(md, editor=True, after=newest, expected=[_token(_TEXT)])
    assert res["ok"] is True and res.get("pending") is not True and "error" not in res
    assert _line(md, 5) == newest, "his newest text is what the file holds"
    row = _rows(md)[-1]
    assert row["kind"] == "author-rewrite" and row["anchor"]["applied"] is True
    assert row["anchor"]["superseded"] == first, "the replaced bytes are kept in the applied row"
    assert res["receipt"]["superseded"] == first


def test_the_authors_edit_over_an_agent_change_replaces_it_and_keeps_the_agents_bytes(tmp_path):
    md = _md(tmp_path)
    agent_text = _TEXT.replace("lazy dog.", "lazy dog, wrote the agent.")
    assert _write(md, editor=False, after=agent_text)["ok"]
    mine = _TEXT + " Mine."
    res = _write(md, editor=True, after=mine)
    assert res["ok"] is True and res.get("pending") is not True
    assert _line(md, 5) == mine
    assert _rows(md)[-1]["anchor"]["superseded"] == agent_text


def test_a_moved_span_is_found_by_its_bytes_and_nothing_else_is_overwritten(tmp_path):
    md = _md(tmp_path)
    path = md / "N1.tex"
    path.write_text(_N1.replace("% N1-p1\n", "% N1-p1\nA line added above by someone else.\n\n"), encoding="utf-8")
    res = _write(md, editor=True, after=_TEXT + " Placed.")
    assert res["ok"] is True and res["applied"]["lines"] == [7, 7]
    text = path.read_text(encoding="utf-8")
    assert "A line added above by someone else." in text and _TEXT + " Placed." in text
    assert "superseded" not in _rows(md)[-1]["anchor"]


def test_an_unlocatable_span_is_the_one_refusal_and_writes_nothing(tmp_path):
    md = _md(tmp_path)
    before = (md / "N1.tex").read_bytes()
    res = _write(md, editor=True, before="Text that is in no line.", span=(40, 40))
    assert res["reason"] == "passage-not-located" and res["refused"]["kind"] == "unknown-home"
    assert (md / "N1.tex").read_bytes() == before and _rows(md) == []


def test_a_stale_base_agent_write_is_still_refused_and_the_file_is_not_written(tmp_path):
    """Agent writes keep the WRITING-CONSOLIDATION-W1 gate: a stale `before` banks a pending row
    (never a splice), and a current token with an overlapping stale edit is refused outright."""
    md = _md(tmp_path)
    path = md / "N1.tex"
    path.write_text(_N1.replace("the lazy dog.", "the sleepy dog."), encoding="utf-8")
    moved = path.read_text(encoding="utf-8")
    res = _write(md, editor=False, after=_TEXT.replace("lazy", "idle"))
    assert res["pending"] is True and res["applied"] is None
    assert res["receipt"]["refused"]["kind"] == "identity-stale"
    assert path.read_text(encoding="utf-8") == moved, "a stale agent write never splices"
    current = _line(md, 5)
    refused = _write(md, editor=False, after=_TEXT.replace("lazy", "idle"),
                     passage_before="lazy", passage_after="idle", expected=[_token(current)])
    assert refused["refused"]["kind"] == "state-not-reached"
    assert path.read_text(encoding="utf-8") == moved


def test_the_tex_panes_block_flip_keeps_the_gate(tmp_path):
    """Only the editor's typed edits are the author path; the TeX pane's block flip is unchanged."""
    md = _md(tmp_path)
    path = md / "N1.tex"
    path.write_text(_N1.replace("lazy dog.\n", "lazy dog. Moved.\n"), encoding="utf-8")
    res = _write(md, editor=True, after=_TEXT + " Flip.", source="block-flip")
    assert res["pending"] is True
    assert "Flip." not in path.read_text(encoding="utf-8")


def test_inserted_above_and_his_paragraph_edited_his_text_replaces_his_own_paragraph(tmp_path):
    """judge-r1 D2 (probe_wrong_paragraph.py): another writer inserts a paragraph above his AND edits his.
    His line numbers now name the inserted paragraph; the door must find his own by its words and leave
    the inserted one intact, never write over the lines at his old numbers."""
    md = _md(tmp_path)
    path = md / "N1.tex"
    path.write_text(_N1.replace("% N1-p1\n", "% N1-p1\nAn inserted paragraph by someone else.\n\n")
                    .replace("lazy dog.\n", "lazy dog, said the agent.\n", 1), encoding="utf-8")
    mine = _TEXT + " Mine."
    res = _write(md, editor=True, after=mine)
    assert res["ok"] is True and res["applied"]["lines"] == [7, 7]
    text = path.read_text(encoding="utf-8")
    assert "An inserted paragraph by someone else." in text, "the paragraph at his old line numbers is untouched"
    assert mine in text and "lazy dog, said the agent." not in text, "his text replaced his own paragraph"
    assert res["receipt"]["superseded"] == _TEXT.replace("lazy dog.", "lazy dog, said the agent.")


def test_his_paragraph_named_by_its_paragraph_id_is_found_after_a_wholesale_rewrite(tmp_path):
    md = _md(tmp_path)
    path = md / "N1.tex"
    path.write_text("% N1-p0\nA paragraph added above by someone else.\n\n"
                    + _N1.replace(_TEXT, "Entirely different words now stand here."), encoding="utf-8")
    mine = _TEXT + " Mine."
    res = _write(md, editor=True, after=mine, block="N1.tex#N1-p1")
    assert res["ok"] is True
    lines = path.read_text(encoding="utf-8").split("\n")
    assert lines[res["applied"]["lines"][0] - 2] == "% N1-p1" and lines[res["applied"]["lines"][0] - 1] == mine
    assert "A paragraph added above by someone else." in lines


def test_a_paragraph_neither_bytes_id_nor_words_locate_is_refused_and_nothing_is_written(tmp_path):
    md = _md(tmp_path)
    path = md / "N1.tex"
    path.write_text(_N1.replace("% N1-p1\n", "% N1-p1\nAn inserted paragraph by someone else.\n\n")
                    .replace(_TEXT, "Entirely different words now stand here."), encoding="utf-8")
    before = path.read_bytes()
    res = _write(md, editor=True, after=_TEXT + " Mine.")
    assert res["reason"] == "passage-not-located" and "error" in res
    assert path.read_bytes() == before and _rows(md) == []


def test_among_near_repeated_paragraphs_the_one_still_at_his_line_is_his(tmp_path):
    """A tie of words (paragraphs nearly alike) is broken by his line; the line never chooses alone, and a
    near-repeat elsewhere is left untouched."""
    md = _md(tmp_path)
    path = md / "N1.tex"
    path.write_text(_N1.replace("lazy dog.\n", "lazy dog, said the agent.\n", 1)
                    + "\n% N1-p3\nThe quick brown fox jumps over the lazy dog again.\n", encoding="utf-8")
    mine = _TEXT + " Mine."
    res = _write(md, editor=True, after=mine)
    assert res["ok"] is True and res["applied"]["lines"] == [5, 5]
    text = path.read_text(encoding="utf-8")
    assert "The quick brown fox jumps over the lazy dog again." in text and "said the agent" not in text


# ── wave 14b, the record's item 1: his paragraph put back at its place ─────────────────────────────────
_THREE = ("\\section{Garden}\n\n"
          "Rain gauges and soil probes were the whole of the method.\n\n"
          "Bees visited the borage most mornings in July, never after the wind turned.\n\n"
          "The compost heap reached sixty degrees within a week of turning.\n")
_BEES = "Bees visited the borage most mornings in July, never after the wind turned."


def _three(tmp_path: Path) -> Path:
    md = _md(tmp_path)
    (md / "N1.tex").write_text(_THREE.replace(_BEES + "\n\n", ""), encoding="utf-8")   # another writer deleted it
    return md


def test_keep_after_passage_not_located_puts_his_paragraph_back_at_its_place(tmp_path):
    """His paragraph (line 5) was deleted by another writer; the door said passage-not-located; Keep my text
    and save it sends the same edit with `placement: insert`, and the door puts his paragraph back at line 5
    as a paragraph of its own: nothing overwritten, one applied row that says so."""
    md = _three(tmp_path)
    mine = _BEES + " I counted forty bees on Sunday."
    refused = _write(md, editor=True, before=_BEES, after=mine, span=(5, 5))
    assert refused["reason"] == "passage-not-located" and _rows(md) == []
    res = _write(md, editor=True, before=_BEES, after=mine, span=(5, 5), placement="insert")
    assert res["ok"] is True and res.get("pending") is not True and res["applied"]["lines"] == [5, 5]
    assert (md / "N1.tex").read_text(encoding="utf-8") == _THREE.replace(_BEES, mine)
    row = _rows(md)[-1]
    assert row["kind"] == "author-rewrite" and row["anchor"]["applied"] is True
    assert row["anchor"]["placement"] == "inserted" and row["anchor"]["before"] == "" and row["anchor"]["basis"] == _BEES
    assert "superseded" not in row["anchor"] and res["receipt"]["inserted"] is True
    assert res["receipt"]["words"].startswith("put your paragraph back at N1.tex:5-5")


def test_the_insert_goes_to_a_paragraph_boundary_and_never_splits_a_paragraph(tmp_path):
    """His line now falls inside a two-line paragraph: his paragraph goes before that paragraph's first line,
    never between its lines; past the end of the file it goes after the last paragraph."""
    md = _md(tmp_path)
    path = md / "N1.tex"
    path.write_text("\\section{Garden}\n\nFirst line of a paragraph\nand its second line.\n", encoding="utf-8")
    res = _write(md, editor=True, before=_BEES, after=_BEES + " Mine.", span=(4, 4), placement="insert")
    assert res["applied"]["lines"] == [3, 3]
    assert path.read_text(encoding="utf-8") == ("\\section{Garden}\n\n" + _BEES + " Mine.\n\n"
                                                "First line of a paragraph\nand its second line.\n")
    res = _write(md, editor=True, before="Gone at the end.", after="Gone at the end, kept.", span=(40, 40), placement="insert")
    assert res["ok"] is True and path.read_text(encoding="utf-8").endswith("second line.\n\nGone at the end, kept.\n")
    assert res["applied"]["lines"] == [8, 8]


def test_a_located_paragraph_is_replaced_not_inserted_even_with_placement_insert(tmp_path):
    """`placement: insert` is used only when nothing locates his paragraph: found by its words, it is
    replaced as before and nothing is added."""
    md = _md(tmp_path)
    path = md / "N1.tex"
    path.write_text(_N1.replace("lazy dog.\n", "lazy dog, said the agent.\n", 1), encoding="utf-8")
    res = _write(md, editor=True, after=_TEXT + " Mine.", placement="insert")
    assert res["applied"]["lines"] == [5, 5] and "said the agent" not in path.read_text(encoding="utf-8")
    assert path.read_text(encoding="utf-8").count("The quick brown fox") == 1 and "placement" not in _rows(md)[-1]["anchor"]


def test_placement_insert_from_an_agent_is_not_the_author_path(tmp_path):
    """An agent write cannot use the insert: it keeps the gate and banks pending, and the file is unchanged."""
    md = _three(tmp_path)
    before = (md / "N1.tex").read_bytes()
    res = _write(md, editor=False, before=_BEES, after=_BEES + " Agent.", span=(5, 5), placement="insert")
    assert res.get("pending") is True and (md / "N1.tex").read_bytes() == before
