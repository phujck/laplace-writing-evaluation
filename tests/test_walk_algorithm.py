from laplace.manuscript import walk


def _all(value):
    if isinstance(value, dict):
        if value.get("t"):
            yield value
        for child in value.values():
            yield from _all(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all(child)


def test_algorithm_comments_math_and_macro_arguments_do_not_mint_control_steps():
    source = ("% \\If{fiction}\\State hidden\n"
              "$\\Return$ \\(\\If\\) "
              "\\texttt{\\If{literal}} \\Unknown{\\State nested}\n"
              "\\State Real\n"
              "\\If{$x>0$}\\Comment{kept condition}\\EndIf")
    pieces = walk.algorithm_pieces(source, {}, 0)
    typed = list(_all(pieces))
    keywords = [piece["s"] for piece in typed if piece["t"] == "algorithm-keyword"]

    assert keywords == ["", "if ", " ▷ ", "end if"]
    assert "fiction" not in walk._flatten_pieces(pieces)
    assert "hidden" not in walk._flatten_pieces(pieces)
    assert any(piece["t"] == "math" and r"\Return" in piece["s"] for piece in typed)
    assert any(piece["t"] == "math" and r"\If" in piece["s"] for piece in typed)
    assert not any(piece["t"] == "algorithm-keyword" and
                   source[piece["o_start"]:piece["o_end"]].startswith(r"\texttt")
                   for piece in typed)
    for piece in typed:
        assert 0 <= piece["o_start"] <= piece["o_end"] <= len(source)


def test_real_algorithm_conditions_comments_and_returns_remain_typed():
    source = (r"\Require{Input $x$}" "\n"
              r"\If{$x>0$}\State $y\gets x$\Comment{positive branch}"
              r"\Else\State $y\gets -x$\EndIf" "\n"
              r"\Return{$y$}")
    pieces = walk.algorithm_pieces(source, {}, 17)
    typed = list(_all(pieces))
    keywords = [piece["s"] for piece in typed if piece["t"] == "algorithm-keyword"]

    assert keywords == ["Require: ", "if ", "", " ▷ ", "else", "", "end if", "return "]
    assert any(piece["t"] == "text" and "positive branch" in piece["s"] for piece in typed)
    assert any(piece["t"] == "math" and piece["s"] == "x>0" for piece in typed)
    assert all(17 <= piece["o_start"] <= piece["o_end"] <= 17 + len(source)
               for piece in typed)
