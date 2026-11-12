"""The ref grammar: a stored source ref names CONTENT, not an offset.

Why this file exists. A builder that LOCATES an anchor honestly and then stores the located
LINE NUMBER has typed a fact about the whole file into a fact about one node. Insert a line
anywhere above it and every ref below moves, the emitted artefact's bytes move, and the
byte-stability probe of a downstream project goes red because something upstream and
unrelated gained a line. That happened twice in one day to a compiled overlay in this repo.
``laplace.manuscript.source_anchor`` is the cure, and these are its clauses:

  (1) a minted anchor round-trips to the span it was minted from;
  (2) INSERTING lines above an anchor does not change the stored anchor — and the derived
      line number follows the prose (the property the whole exercise is for);
  (3) EDITING the anchored text DOES change what resolves — the anchor goes dead rather
      than silently pointing at a neighbour (the floor: located, never guessed);
  (4) content that is not unique is refused at MINT time, not discovered by a reader;
  (5) the legacy offset form still parses, so no existing declaration is orphaned.
"""
from __future__ import annotations

import pytest

from laplace.manuscript import source_anchor as sa

LINES = [
    "# a root document",
    "",
    "the anchored claim: the price of counting is not the price of authority",
    "some other line",
    "a trailing line",
]


def test_1_a_minted_anchor_round_trips():
    for start, end in ((1, 1), (3, 3), (2, 4), (1, len(LINES))):
        ref = sa.anchor(LINES, start, end)
        assert sa.locate(LINES, ref) == (start, end)
        span = end - start + 1
        assert ("+" in ref) == (span > 1), ref
        assert sa.is_content_anchor(ref)


def test_2_an_insertion_above_the_anchor_leaves_the_stored_bytes_alone():
    """THE DEFECT, killed. The same prose, pushed down the file, keeps its ref."""
    before = sa.anchor(LINES, 3)
    shifted = ["a brand new heading", "", "and another inserted line", *LINES]
    after = sa.anchor(shifted, 6)
    assert after == before, "the anchor moved when only the offset did"
    # ... and the line number is DERIVED, so a reader still lands on the prose
    assert sa.locate(LINES, before) == (3, 3)
    assert sa.locate(shifted, before) == (6, 6)


def test_3_editing_the_anchored_text_kills_the_anchor_rather_than_sliding_it():
    ref = sa.anchor(LINES, 3)
    edited = list(LINES)
    edited[2] = edited[2].replace("the price of counting", "the cost of counting")
    with pytest.raises(sa.AnchorError) as e:
        sa.locate(edited, ref)
    assert "no longer in this source" in str(e.value)


def test_4_content_that_is_not_unique_is_refused_at_mint_time():
    doubled = ["same line", "different", "same line"]
    with pytest.raises(sa.AnchorError) as e:
        sa.anchor(doubled, 1)
    assert "not unique" in str(e.value)


def test_5_the_legacy_offset_form_still_parses_and_is_still_bounded():
    assert sa.locate(LINES, "3") == (3, 3)
    assert sa.locate(LINES, "2-4") == (2, 4)
    assert not sa.is_content_anchor("3")
    with pytest.raises(sa.AnchorError):
        sa.locate(LINES, "99")
    with pytest.raises(sa.AnchorError):
        sa.parse_ref("no locator at all")


def test_6_resolve_and_display_derive_the_line_at_read_time(tmp_path):
    (tmp_path / "doc.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    ref = f"doc.md:{sa.anchor(LINES, 2, 4)}"
    assert sa.resolve(ref, tmp_path) == ("doc.md", 2, 4)
    assert sa.display(ref, tmp_path) == "doc.md:2-4"
    assert sa.display(f"doc.md:{sa.anchor(LINES, 3)}", tmp_path) == "doc.md:3"
    with pytest.raises(sa.AnchorError) as e:
        sa.resolve("nowhere.md:1", tmp_path)
    assert "missing file" in str(e.value)
