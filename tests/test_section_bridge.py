"""test_section_bridge.py — THE SECTION BRIDGE (``pipeline.section_bridge.bridged_network``).

The bridge is the audit's readiness precondition, productized: a single-file inline-``\\section``
paper is split into the ``\\input{}`` layout the proven UP operator
(``corpus_ingest.build_corpus_network``) consumes, an ``\\input``-layout paper passes through
unbridged, and the source tree is NEVER written. These tests are hermetic BY CONSTRUCTION — they
synthesise tiny .tex fixtures under pytest's ``tmp_path`` (no real corpus, no network, no
embedding) and assert the contract:

  * a single-file inline-``\\section`` paper BRIDGES to a multi-node conceptric (>2 nodes, real
    section/equation nodes — not the 2-node ``paper://``+``references`` degenerate);
  * an ``\\input``-layout paper PASSES THROUGH (``bridged`` False), sections intact;
  * the SOURCE TREE is untouched — no file created or modified under the fixture dir;
  * DETERMINISM — two calls on the same input mint the same node ids (the property the store
    derivers' byte-identical rows rest on);
  * a paper with neither inline ``\\section`` nor a resolving ``\\input`` layout RAISES
    ``SectionBridgeError`` (named, never a silent 2-node conceptric).
"""
from __future__ import annotations

import pytest

from laplace.pipeline.section_bridge import SectionBridgeError, bridged_network

# --------------------------------------------------------------------------- #
# tiny synthetic fixtures (hermetic — no real corpus)
# --------------------------------------------------------------------------- #
_SINGLE_FILE_TEX = r"""\documentclass{article}
\begin{document}
\section{Introduction}\label{sec:intro}
This is the real introduction prose describing the motivation of the work in his own
voice at some length so that it is nontrivial content and not merely a title fragment.

\section{The Method}\label{sec:method}
We now derive the key relation from first principles.
\begin{equation}\label{eq:base}
a = b
\end{equation}
From \eqref{eq:base} the next step follows directly:
\begin{equation}\label{eq:step}
c = a + 1
\end{equation}
\end{document}
"""

_MAIN_INPUT_TEX = r"""\documentclass{article}
\begin{document}
% please do not use \input{forbidden} anywhere in the body
\input{sec_a}
\input{sec_b}
\end{document}
"""
_SEC_A_TEX = r"""\section{Alpha}\label{sec:alpha}
Alpha section prose about the first idea, at enough length to be real content.
"""
_SEC_B_TEX = r"""\section{Beta}\label{sec:beta}
Beta section prose introducing an equation.
\begin{equation}\label{eq:x}
x = y
\end{equation}
"""


def _write_single_file(dir_path) -> "object":
    tex = dir_path / "paper.tex"
    tex.write_text(_SINGLE_FILE_TEX, encoding="utf-8")
    return tex


def _write_input_layout(dir_path) -> "object":
    (dir_path / "sec_a.tex").write_text(_SEC_A_TEX, encoding="utf-8")
    (dir_path / "sec_b.tex").write_text(_SEC_B_TEX, encoding="utf-8")
    main = dir_path / "main.tex"
    main.write_text(_MAIN_INPUT_TEX, encoding="utf-8")
    return main


def _dir_snapshot(dir_path) -> dict[str, bytes]:
    """Every file under ``dir_path`` -> its bytes (the source-tree-untouched witness)."""
    return {str(p.relative_to(dir_path)): p.read_bytes()
            for p in sorted(dir_path.rglob("*")) if p.is_file()}


def _kinds(net) -> dict[str, int]:
    counts: dict[str, int] = {}
    for n in net["nodes"].values():
        counts[n.get("kind", "?")] = counts.get(n.get("kind", "?"), 0) + 1
    return counts


# --------------------------------------------------------------------------- #
# a single-file inline-\section paper bridges to a multi-node net
# --------------------------------------------------------------------------- #
def test_single_file_bridges_to_multi_node_net(tmp_path):
    tex = _write_single_file(tmp_path)
    net = bridged_network(tex, "synthetic-single")

    assert net["bridged"] is True
    assert net["paper_id"] == "synthetic-single"
    # NOT the 2-node degenerate (paper:// + references only): real sections + equations landed.
    assert len(net["nodes"]) > 2
    kinds = _kinds(net)
    assert kinds.get("section", 0) == 2                 # two inline \section blocks
    assert kinds.get("equation", 0) == 2                # both equations atomised
    # the section ids are the block \labels (the atomiser's own rule), enrichment keyed to them
    assert "sec:intro" in net["nodes"] and "sec:method" in net["nodes"]
    assert set(net["section_prose"]) == {"sec:intro", "sec:method"}
    assert "real introduction prose" in net["section_prose"]["sec:intro"]
    # the eq->eq dependency edge survives (eq:step \eqref's eq:base)
    assert "eq:base" in net["edge_index"].get("eq:step", [])


def test_bridge_does_not_write_the_source_tree(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    tex = _write_single_file(src)
    before = _dir_snapshot(src)
    bridged_network(tex, "synthetic-single")
    after = _dir_snapshot(src)
    # no file created, none mutated — the split landed in the bridge's OWN tempdir
    assert before == after, "bridge wrote inside the source tree"
    assert set(after) == {"paper.tex"}


def test_bridge_honours_explicit_workdir_and_never_source(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    tex = _write_single_file(src)
    work = tmp_path / "work"
    before = _dir_snapshot(src)
    net = bridged_network(tex, "synthetic-single", workdir=work)
    # the split landed under the EXPLICIT workdir, the source tree stayed frozen
    assert (work / "synthetic-single" / "main.tex").is_file()
    assert _dir_snapshot(src) == before
    assert net["bridged"] is True


# --------------------------------------------------------------------------- #
# an \input-layout paper passes through unbridged (detect, don't force)
# --------------------------------------------------------------------------- #
def test_input_layout_passes_through_unbridged(tmp_path):
    main = _write_input_layout(tmp_path)
    before = _dir_snapshot(tmp_path)
    net = bridged_network(main, "synthetic-input")

    assert net["bridged"] is False                      # detected, not forced through the splitter
    kinds = _kinds(net)
    assert kinds.get("section", 0) == 2
    assert "sec:alpha" in net["nodes"] and "sec:beta" in net["nodes"]
    assert kinds.get("equation", 0) == 1
    # prose read IN PLACE from the \input'd files, keyed to the net's own ids
    assert set(net["section_prose"]) == {"sec:alpha", "sec:beta"}
    assert "Alpha section prose" in net["section_prose"]["sec:alpha"]
    # pass-through is pure read: the source tree is untouched
    assert _dir_snapshot(tmp_path) == before


# --------------------------------------------------------------------------- #
# determinism — same input, same node ids
# --------------------------------------------------------------------------- #
def test_bridge_is_deterministic(tmp_path):
    tex = _write_single_file(tmp_path)
    net_a = bridged_network(tex, "synthetic-single")
    net_b = bridged_network(tex, "synthetic-single")
    # node ids are independent of the (per-call, different) tempdir path
    assert set(net_a["nodes"]) == set(net_b["nodes"])
    assert net_a["section_prose"] == net_b["section_prose"]
    assert net_a["section_meta"] == net_b["section_meta"]
    assert net_a["edge_index"] == net_b["edge_index"]


# --------------------------------------------------------------------------- #
# a paper with no sections and no \input layout cannot be bridged
# --------------------------------------------------------------------------- #
def test_no_sections_no_input_raises(tmp_path):
    tex = tmp_path / "flat.tex"
    tex.write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "Just body prose with no sectioning at all and no inputs.\n"
        "\\end{document}\n", encoding="utf-8")
    with pytest.raises(SectionBridgeError) as ei:
        bridged_network(tex, "flat-paper")
    assert ei.value.paper_id == "flat-paper"


def test_commented_out_sections_are_not_bridged(tmp_path):
    """A paper whose only \\section lines are LaTeX comments (the superoscillations shape) has
    nothing real to split — the bridge refuses rather than emit a 2-node conceptric."""
    tex = tmp_path / "commented.tex"
    tex.write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "% \\section*{Results}\n% \\section{Discussion}\n"
        "Only commented-out sections above; the body itself has no live sectioning.\n"
        "\\end{document}\n", encoding="utf-8")
    with pytest.raises(SectionBridgeError):
        bridged_network(tex, "commented-paper")


# --------------------------------------------------------------------------- #
# THE SECTION LENS KEEPS THE MATH (WO-20260820-extraction-lens-keeps-math)
# --------------------------------------------------------------------------- #
def test_section_prose_keeps_his_math(tmp_path):
    """A section's ``embed_text`` carries the numbers. The measured defect was the reverse: the
    bridge stripped math, so ``section_architecture`` rows read "In all cases, we use " where the
    paper says ``$L=10$`` sites at ``$t_0=0.52$`` eV — grammatical, and physically empty."""
    tex = tmp_path / "numbers.tex"
    tex.write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "\\section{Numerical Illustrations}\\label{sec:num}\n"
        "In all cases, we use an $L=10$ site system with hopping $t_0 = 0.52$ eV "
        "and drive amplitude $F_0 = 10$ MV/cm.\n"
        "\\end{document}\n", encoding="utf-8")
    net = bridged_network(tex, "numbers-paper")
    prose = " ".join(net["section_prose"].values())
    assert "$L=10$" in prose and "$t_0 = 0.52$ eV" in prose and "$F_0 = 10$ MV/cm" in prose


def test_prose_window_spends_its_budget_on_prose_not_on_latex():
    """The window is budgeted in PROSE. A long math span costs nothing, so keeping the math cannot
    push a sentence that used to fit out of the head — the regression that ate the very sentence
    this work order is named for."""
    from laplace.pipeline.section_bridge import _prose_window
    from laplace.engine.voice_corpus_ingest import demath

    heavy = "$\\hat{H} = \\sum_j t_0 \\hat{c}^\\dagger_j \\hat{c}_{j+1} + U \\hat{n}_j$"
    prose = (("word " * 100) + heavy + " the marker sentence survives. "
             + ("filler " * 400)).strip()
    win = _prose_window(prose)
    assert " ... " in win                                   # it really did window
    assert heavy in win                                     # the math rode along
    assert "the marker sentence survives." in win           # and cost it nothing
    # the head holds a full prose budget, not a budget spent on backslashes
    head = win.split(" ... ")[0]
    assert len(" ".join(demath(head).split())) > 500


def test_prose_window_is_byte_identical_when_there_is_no_math():
    """No math, no change: a math-free section windows exactly as the demo rule windowed it."""
    from laplace.pipeline.section_bridge import _HEAD, _TAIL, _prose_window

    prose = "alpha " * 500
    assert _prose_window(prose) == prose[:_HEAD] + " ... " + prose[-_TAIL:]


def test_a_real_display_equation_survives_in_the_walk_lens_not_the_section_lens(tmp_path):
    """THE DECLARED DIVISION OF LABOUR, PINNED ON A REAL EQUATION.

    ``strip_latex``'s docstring rests the paragraph-shape invariant on a claim it never proved:
    a DISPLAY equation is dropped from the section/paragraph lens because *the display equations
    live in ``spine_chain`` / ``derivation_walk`` where they belong*. Un-pinned, that is exactly
    the shape of the loss this work order was raised for — a number vanishing while the sentence
    around it stays grammatical, and nothing anywhere signalling it.

    So both halves are asserted on ONE source: an equation carrying real numeric literals is
    ABSENT from the section prose (the invariant holds, deliberately), and the SAME equation is
    present verbatim in its ``derivation_walk`` row (the arcana was moved, not deleted). Break
    either half and the drop stops being a division of labour and becomes a second mutilation.
    """
    from laplace.pipeline.stage_store import derive_derivation_walk

    tex = tmp_path / "walk.tex"
    tex.write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "\\section{Model}\\label{sec:model}\n"
        "We drive a chain of $L=10$ sites, written at length so the section carries real prose "
        "and is not a bare title fragment, with the hopping fixed throughout the study.\n"
        "\\begin{equation}\\label{eq:ham}\n"
        "\\hat{H} = -0.52 \\sum_j \\hat{c}^\\dagger_j \\hat{c}_{j+1} + 32.7 \\hat{n}_j\n"
        "\\end{equation}\n"
        "From \\eqref{eq:ham} the drive follows, at similar length so this paragraph too is real "
        "content and clears the band the passage filter applies downstream.\n"
        "\\begin{equation}\\label{eq:drive}\n"
        "F(t) = 10 \\sin(32.7 t)\n"
        "\\end{equation}\n"
        "\\end{document}\n", encoding="utf-8")
    net = bridged_network(tex, "walk-paper")

    # half one: the section lens drops the display — the paragraph-shape invariant, deliberately
    prose = " ".join(net["section_prose"].values())
    assert "$L=10$" in prose                                  # inline math still rides along
    assert "\\hat{c}^\\dagger_j" not in prose

    # half two: the walk lens carries that same equation, numbers intact
    walk = " ".join(r["embed_text"] for r in derive_derivation_walk(net, "walk-paper"))
    assert "\\hat{c}^\\dagger_j" in walk
    assert "0.52" in walk and "32.7" in walk


# --------------------------------------------------------------------------- #
# THE MIDDLE STOPS SWALLOWING THE ARCANA (WO-20260820-section-window-caps-the-arcana)
# --------------------------------------------------------------------------- #
def _long_section_with_buried_arcana() -> str:
    """A section whose arcana sit squarely in the elided middle: 600 chars of opening prose, the
    methods sentences, then 600+ chars of closing prose. The measured shape of ``SA-nuodfgnl-s2``.
    """
    opening = ("We open by restating the claim in the plainest terms available to us here. " * 12)
    middle = ("The drive frequency is $\\omega_0 = 32.7$ THz throughout. "
              "The lattice constant is $a = 4$ nm and the field amplitude is $F_0 = 10$ MV/cm. "
              "Calculations are implemented via the QuSpin package in Python. ")
    closing = ("We close by restating the consequence in the plainest terms available. " * 12)
    return " ".join((opening + middle + closing).split())


def test_salvage_band_carries_the_middles_arcana():
    """The head+tail window elides the middle, and the middle is where his methods paragraph lives.
    The measured casualty was ``SA-nuodfgnl-s2``: ``\\omega_0 = 32.7`` THz, ``F_0 = 10`` MV/cm and
    ``QuSpin`` all inside the ellipsis, absent from ``embed_text`` entirely. The salvage band buys
    them back."""
    from laplace.pipeline.section_bridge import _prose_window

    win = _prose_window(_long_section_with_buried_arcana())
    assert win.count(" ... ") == 2                       # head ... salvage ... tail
    assert "32.7" in win and "MV/cm" in win and "QuSpin" in win
    assert win.startswith("We open by restating")        # the head is still the head
    assert win.endswith("terms available.")              # and the tail is still the tail


def test_salvage_band_never_fires_on_arcana_free_prose():
    """A middle carrying no arcana salvages nothing, and the window is the demo's rule byte-for-
    byte — the invariant that makes this change safe to re-mint an existing store under."""
    from laplace.pipeline.section_bridge import _HEAD, _TAIL, _prose_window

    prose = " ".join(("Connective prose that states no quantity whatsoever. " * 60).split())
    assert _prose_window(prose) == prose[:_HEAD] + " ... " + prose[-_TAIL:]


def test_narrowing_for_the_model_window_carries_arcana_out_of_the_head():
    """When the window must shrink to fit the embedder, a narrowed-off sentence that CARRIES
    ARCANA rejoins the salvage band rather than leaving — so shrinking the head can never silently
    cost the reader the very ``$t_0 = 0.52$ eV`` line the previous work order won back."""
    from laplace.pipeline import section_bridge as sb

    if sb._tokenizer() is None:
        import pytest
        pytest.skip("no vendored tokenizer — no embedder here for the window to be honest about")

    head = ("A dense preamble sentence with $\\hat{H} = \\sum_j t_0 \\hat{c}^\\dagger_j "
            "\\hat{c}_{j+1} + U \\hat{n}_j$ carrying weight. " * 8)
    marker = "In all cases, we use a hopping parameter $t_0 = 0.52$ eV. "
    body = ("Some connective prose with $\\Phi(t)$ and $\\Psi(t)$ in it. " * 40)
    tail = ("A closing consequence stated at length for the reader. " * 12)
    prose = " ".join((head + marker + body + tail).split())

    win = sb._prose_window(prose)
    assert sb._model_tokens(win) <= sb._MODEL_TOKENS      # it really fits what the model reads
    assert "0.52" in win                                  # and the arcana rode the narrowing out


def test_the_window_is_what_the_embedder_reads():
    """``embed_text`` never exceeds the embedding model's own window. It used to: measured
    2026-08-21 on the live store, ``SA-dgoenzbv-s1`` was 595 wordpiece tokens and ``SA-wor2-s4``
    549, both cut by fastembed with nothing said — a prose-character budget cannot bound
    wordpieces, because his LaTeX costs ~2.9 chars/token where his prose costs ~5."""
    from laplace.pipeline import section_bridge as sb

    if sb._tokenizer() is None:
        import pytest
        pytest.skip("no vendored tokenizer — no embedder here for the window to be honest about")

    heavy = ("The operator $\\hat{U}=U\\sum_j \\hat{c}^\\dagger_{j \\uparrow}"
             "\\hat{c}_{j \\uparrow} \\hat{c}^\\dagger_{j \\downarrow}\\hat{c}_{j \\downarrow}$ "
             "at $U = 2.5$ eV and $\\omega_0 = 32.7$ THz. ")
    prose = " ".join((heavy * 30).split())
    assert sb._model_tokens(sb._prose_window(prose)) <= sb._MODEL_TOKENS
