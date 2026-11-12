import json

from laplace.pipeline.authored_closure import check_authored_closure


def _write_contract(path):
    path.write_text(json.dumps({
        "roadmap": {
            "section": "S1",
            "ordered_section_refs": ["sec:S2", "sec:S3"],
        },
        "dependency_links": [{
            "source": "S3",
            "requires": ["eq:law", "fig:data"],
        }],
        "numbered_objects": ["eq:law", "fig:data"],
    }), encoding="utf-8")


def test_authored_closure_accepts_roadmap_and_dependencies(tmp_path):
    tex = tmp_path / "main.tex"
    tex.write_text(r"""
\section{Introduction}\label{sec:S1}
The problem is physical.

Section~\ref{sec:S2} defines the model and Sec.~\ref{sec:S3} tests it.
\section{Model}\label{sec:S2}
\begin{equation}x=1\label{eq:law}\end{equation}
\section{Results}\label{sec:S3}
Equation~\eqref{eq:law} predicts the transition shown in Fig.~\ref{fig:data}.
\begin{figure}\caption{Data}\label{fig:data}\end{figure}
""", encoding="utf-8")
    contract = tmp_path / "closure.json"
    _write_contract(contract)
    assert check_authored_closure(tex, contract)["pass"] is True


def test_authored_closure_rejects_misplaced_roadmap_and_missing_link(tmp_path):
    tex = tmp_path / "main.tex"
    tex.write_text(r"""
\section{Introduction}\label{sec:S1}
Section~\ref{sec:S2} defines the model and Sec.~\ref{sec:S3} tests it.

The problem is physical.
\section{Model}\label{sec:S2}
\begin{equation}x=1\label{eq:law}\end{equation}
\section{Results}\label{sec:S3}
The transition is visible.
\begin{figure}\caption{Data}\label{fig:data}\end{figure}
""", encoding="utf-8")
    contract = tmp_path / "closure.json"
    _write_contract(contract)
    result = check_authored_closure(tex, contract)
    assert result["pass"] is False
    kinds = {finding["kind"] for finding in result["findings"]}
    assert "closure-roadmap-missing" in kinds
    assert "closure-dependency-unlinked" in kinds
    assert "closure-object-orphan" in kinds
