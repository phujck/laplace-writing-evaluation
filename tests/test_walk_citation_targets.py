"""Pre-build local bibliography targets for the manuscript citation picker."""
from __future__ import annotations

import json

from laplace.manuscript import walk


def test_citation_targets_join_selected_bib_inline_and_association_without_network(tmp_path):
    root = tmp_path / "main.tex"
    root.write_text("\\documentclass{article}\n\\bibliography{sources}\n"
                    "\\begin{document}\n\\begin{thebibliography}{9}\n"
                    "\\bibitem{inline} Inline title (2022).\n"
                    "\\end{thebibliography}\n\\end{document}\n", encoding="utf-8")
    (tmp_path / "sources.bib").write_text(
        "@article{local, title={Local {Title}}, year={2024}}\n", encoding="utf-8")
    (tmp_path / "references.json").write_text(json.dumps({"associations": [{
        "citekey": "attached", "metadata": {"title": "Attached title", "year": "2023"}}]}),
        encoding="utf-8")

    source_tree = {"sources": [{"file": "main.tex", "text": root.read_text(encoding="utf-8")}]}
    targets = walk.citation_targets(root, tmp_path, source_tree, {})
    by_key = {row["key"]: row for row in targets}

    assert by_key["local"] == {"key": "local", "title": "Local Title", "year": "2024", "source": "sources.bib"}
    assert by_key["inline"]["title"].startswith("Inline title") and by_key["inline"]["year"] == "2022"
    assert by_key["attached"] == {"key": "attached", "title": "Attached title", "year": "2023", "source": "association"}
