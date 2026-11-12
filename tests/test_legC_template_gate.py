"""Leg C bite C1 — the template gate is WIRED into the mechanical panel.

``tex_template.check_template`` had NO pipeline caller (a dead gate). It now runs
every round inside ``fixedpoint_mechround.py``'s mechanical panel, alongside
``lint_typography`` and ``check_house_style_manuscript``. Property under test: a
NON-CONFORMING preamble (plain article, no eigen house layer) makes the
``template`` panel entry read clean=False; a conforming REVTeX4-2 + eigen-revtex
preamble reads clean=True. Driven as the REAL script via the planted-failure
runpy idiom.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import planted_fixture as pf

pytestmark = pytest.mark.unit

_FRAGS = {
    "N1": (r"\section{Alpha}\label{sec:a}" "\n"
           "Plain prose about alpha for the reader here, a full sentence.\n"),
}

_ARTICLE_PREAMBLE = "\\documentclass{article}\n"
_REVTEX_PREAMBLE = (
    "\\documentclass[aps,prx,twocolumn]{revtex4-2}\n"
    "\\usepackage{eigen-revtex}\n")


def _env(tmp_path, preamble):
    md = tmp_path / "m"
    md.mkdir(parents=True, exist_ok=True)
    body = (preamble + "\\begin{document}\n"
            + "".join(f"\\input{{{s}}}\n" for s in _FRAGS)
            + "\\end{document}\n")
    (md / "main.tex").write_text(body, encoding="utf-8")
    for stem, content in _FRAGS.items():
        (md / f"{stem}.tex").write_text(content, encoding="utf-8")
    pf.write_plan(md / "plan.json", list(_FRAGS))
    fb = pf.write_feedback(md / "feedback.jsonl", [])
    proj = pf.make_project(plan_path=md / "plan.json")
    return md, fb, proj


def _template_entry(tmp_path, preamble, monkeypatch):
    md, fb, proj = _env(tmp_path, preamble)
    _s, doc = pf.run_mechround(str(md / "main.tex"), "-", str(md / "r.json"),
                               str(fb), str(md), monkeypatch, proj, round_no=1)
    entry = next(p for p in doc["panel"] if p["label"] == "template")
    return entry, doc


def test_nonconforming_preamble_fails_the_panel(tmp_path, monkeypatch):
    entry, doc = _template_entry(tmp_path, _ARTICLE_PREAMBLE, monkeypatch)
    assert entry["clean"] is False              # article + no house layer -> fails
    assert entry.get("failed") is not True      # a real verdict, not a crashed gate
    # evidence-only: the template axis is NOT routed to a section builder
    assert not any("documentclass" in str(f.get("kind"))
                   for f in doc["flags_unrouted"])


def test_conforming_preamble_passes_the_panel(tmp_path, monkeypatch):
    entry, _doc = _template_entry(tmp_path, _REVTEX_PREAMBLE, monkeypatch)
    assert entry["clean"] is True               # revtex4-2 + eigen-revtex -> clean
