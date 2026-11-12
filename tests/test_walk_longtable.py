from pathlib import Path

from laplace.manuscript import walk


def _blocks(text: str):
    return walk.blocks_for(text, file_rel="longtable.tex", repo_file="longtable.tex",
                           md=Path("."), corpus="", dir_param="", para_spans=[],
                           known_macros={})


def _cells(row):
    return [cell["tex"] for cell in row["cells"]]


def test_real_engine_devplan_longtable_separates_caption_controls_and_data_with_offsets():
    source = Path("synthetics papers/engine-devplan/manuscript/whitepaper/A1.tex")
    table = next(block for block in _blocks(source.read_text(encoding="utf-8"))
                 if block["kind"] == "table")

    assert table["env"] == "longtable"
    assert table["caption"].startswith("The claim ledger:")
    assert sum(row["role"] == "first-header" for row in table["rows"]) == 1
    assert not any(row["role"] == "continuation-header" for row in table["rows"])
    assert sum(row["role"] == "continuation-footer" for row in table["rows"]) == 1
    assert _cells(table["rows"][0]) == [
        r"\textbf{Claim}", r"\textbf{Status class}", r"\textbf{Ref handle (kind)}"]
    assert _cells(table["rows"][1]) == [r"\footnotesize continued on next page"]
    assert len([row for row in table["rows"] if row["role"] == "body"]) == 34
    assert all(not any(token in cell["tex"] for token in
                       (r"\caption", r"\label", r"\endfirsthead", r"\endhead",
                        r"\endfoot", r"\endlastfoot"))
               for row in table["rows"] for cell in row["cells"])
    assert all(table["tex"][cell["o_start"]:cell["o_end"]] == cell["tex"]
               for row in table["rows"] for cell in row["cells"])
    assert all(table["tex"][row["o_start"]:row["o_end"]].strip()
               for row in table["rows"])


def test_distinct_longtable_continuation_and_footer_meanings_are_each_preserved_once():
    text = (r"\begin{longtable}{cc}" "\n"
            r"\caption{Meaningful table}\label{tab:meaning}\\" "\n"
            r"First header & Value\\" "\n" r"\endfirsthead" "\n"
            r"Continued header & Value\\" "\n" r"\endhead" "\n"
            r"\multicolumn{2}{r}{Continues on the next page}\\" "\n" r"\endfoot" "\n"
            r"\multicolumn{2}{r}{Final footer meaning}\\" "\n" r"\endlastfoot" "\n"
            r"A & B\\" "\n" r"\end{longtable}" "\n")
    table = _blocks(text)[0]

    assert table["kind"] == "table" and table["caption"] == "Meaningful table"
    assert [(row["role"], _cells(row)) for row in table["rows"]] == [
        ("first-header", ["First header", "Value"]),
        ("continuation-header", ["Continued header", "Value"]),
        ("continuation-footer", ["Continues on the next page"]),
        ("final-footer", ["Final footer meaning"]),
        ("body", ["A", "B"]),
    ]
    assert table["rows"][2]["cells"][0]["colspan"] == 2
    assert table["rows"][3]["cells"][0]["colspan"] == 2
    assert all(table["tex"][cell["o_start"]:cell["o_end"]] == cell["tex"]
               for row in table["rows"] for cell in row["cells"])


def test_longtable_marker_inside_group_is_cell_content_not_section_control():
    text = (r"\begin{longtable}{c}" "\n"
            r"\texttt{literal \endhead token}\\" "\n"
            r"Data\\" "\n" r"\end{longtable}" "\n")
    table = _blocks(text)[0]

    assert table["kind"] == "table"
    assert [row["role"] for row in table["rows"]] == ["body", "body"]
    assert r"\endhead" in table["rows"][0]["cells"][0]["tex"]
