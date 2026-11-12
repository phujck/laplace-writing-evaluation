from pathlib import Path
from walk_source import walk_source

from laplace.manuscript import walk


def _pieces(value):
    if isinstance(value, dict):
        if value.get("t"):
            yield value
        for child in value.values():
            yield from _pieces(child)
    elif isinstance(value, list):
        for child in value:
            yield from _pieces(child)


def test_parbox_keeps_body_offsets_and_separates_geometry_from_content():
    source = (r"Before \parbox[t][4em][c]{0.31\textwidth}{\raggedright "
              r"Body $x$ in \S\ref{sec:one}.\strut} after.")
    pieces = walk.tex_pieces(source, {})
    parbox = next(piece for piece in pieces if piece["t"] == "parbox")
    nested = list(_pieces(parbox["pieces"]))

    assert parbox["geometry"] == {"position": "t", "height": "4em",
                                  "inner_position": "c", "width": r"0.31\textwidth"}
    assert source[parbox["o_start"]:parbox["o_end"]].startswith(r"\parbox[t][4em][c]")
    assert any(piece["t"] == "math" and piece["s"] == "x" for piece in nested)
    assert any(piece["t"] == "symbol" and piece["s"] == "§" for piece in nested)
    assert any(piece["t"] == "ref" and piece["label"] == "sec:one" for piece in nested)
    assert not [piece for piece in nested if piece["t"] == "macro"
                and piece.get("name") in {"raggedright", "strut"}]
    assert all(parbox["o_start"] < piece["o_start"] <= piece["o_end"] < parbox["o_end"]
               for piece in nested)


def test_vertical_skip_commands_are_structural_breaks_and_keep_following_prose():
    source = r"First.\smallskip\noindent Second.\medskip Third.\bigskip Fourth."
    pieces = walk.tex_pieces(source, {})

    assert [piece.get("size") for piece in pieces if piece["t"] == "break"] == [
        "smallskip", "medskip", "bigskip"]
    assert "First." in walk._flatten_pieces(pieces)
    assert "Second." in walk._flatten_pieces(pieces)
    assert "Third." in walk._flatten_pieces(pieces)
    assert "Fourth." in walk._flatten_pieces(pieces)
    assert not [piece for piece in pieces if piece["t"] == "macro"]


def test_section_symbol_is_source_typed_without_changing_reference_identity():
    source = r"See \S\ref{sec:cost} and \S\ref{sec:plan}."
    pieces = walk.tex_pieces(source, {})

    assert [piece["s"] for piece in pieces if piece["t"] == "symbol"] == ["§", "§"]
    assert [piece["label"] for piece in pieces if piece["t"] == "ref"] == [
        "sec:cost", "sec:plan"]
    assert all(source[piece["o_start"]:piece["o_end"]] == r"\S"
               for piece in pieces if piece["t"] == "symbol")


def test_claim_macro_becomes_only_its_exact_declared_provenance_superscript():
    style = Path("synthetics papers/subset-sum-itqde/manuscript/whitepaper/eigen-revtex.sty")
    macros = walk._macros_from(style.read_text(encoding="utf-8"))
    assert macros[r"\claim"] == r"\textsuperscript{\textcolor{phys}{[C#1]}}"

    source = r"Statement.\claim{17}"
    claim = next(piece for piece in walk.tex_pieces(source, macros)
                 if piece["t"] == "provenance-label")
    assert claim["s"] == "[C17]" and claim["value"] == "17"
    assert claim["provenance_kind"] == "declared-claim-tag"
    assert claim["declared_expansion"] == macros[r"\claim"]
    assert source[claim["o_start"]:claim["o_end"]] == r"\claim{17}"
    assert not any(piece["t"] in {"placeholder", "semantic-label", "macro"}
                   for piece in walk.tex_pieces(source, macros))
    simple = {r"\claim": r"\textsuperscript{[C#1]}"}
    assert walk.tex_pieces(r"\claim{2}", simple)[0]["s"] == "[C2]"


def test_superscript_subscript_and_footnote_keep_real_content_and_parent_offsets():
    source = (r"A\textsuperscript{*} B\textsubscript{b}"
              r" C\footnote{Qualified $x$ with \ref{sec:q}.}")
    pieces = walk.tex_pieces(source, {})
    typed = list(_pieces(pieces))
    sup = next(piece for piece in pieces if piece["t"] == "sup")
    sub = next(piece for piece in pieces if piece["t"] == "sub")
    footnote = next(piece for piece in pieces if piece["t"] == "footnote")

    assert sup["s"] == "*" and sub["s"] == "b"
    assert walk._flatten_pieces(footnote["pieces"]) == "Qualified $x$ with sec:q."
    assert any(piece["t"] == "math" and piece["s"] == "x" for piece in typed)
    assert any(piece["t"] == "ref" and piece["label"] == "sec:q" for piece in typed)
    for piece, command in ((sup, r"\textsuperscript{*}"),
                           (sub, r"\textsubscript{b}"),
                           (footnote, r"\footnote{Qualified $x$ with \ref{sec:q}.}")):
        assert source[piece["o_start"]:piece["o_end"]] == command
    assert all(footnote["o_start"] < piece["o_start"] <= piece["o_end"] < footnote["o_end"]
               for piece in _pieces(footnote["pieces"]))


def test_actual_multiline_heading_keeps_balanced_title_tail_and_exact_span():
    source = Path("synthetics papers/subset-sum-itqde/disclosure/main.tex")
    text = source.read_text(encoding="utf-8")
    masked, _ = walk.root_content(text)
    blocks = walk.blocks_for(masked, file_rel="main.tex", repo_file=source.as_posix(),
                             md=source.parent, corpus="", dir_param="", para_spans=[],
                             known_macros=walk._macros_from(text))
    heading = next(block for block in blocks if block["kind"] == "head"
                   and block["src"]["line_start"] == 155)

    assert heading["src"]["line_end"] == 156
    assert heading["title"] == "Post-acquisition selection of location and of every coarser resolution."
    assert heading["tail"].startswith(" From the one record")
    assert walk._flatten_pieces(heading["tail_pieces"]).startswith(" From the one record")
    lines = masked.split("\n")
    assert heading["tex"] == "\n".join(lines[154:156])
    assert all(heading["tex"][piece["o_start"]:piece["o_end"]]
               for piece in heading["title_pieces"] + heading["tail_pieces"])
    assert not any(block["src"]["line_start"] == 156 for block in blocks if block is not heading)


def test_walk_client_renders_parbox_body_as_structural_source_mapped_piece():
    module = walk_source()
    assert 'case "parbox"' in module
    assert "p.geometry||{}" in module
    assert "renderPieces(kids||[],box)" in module
