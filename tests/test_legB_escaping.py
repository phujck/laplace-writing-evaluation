"""legB F1 regression — the attribute-escaping XSS guard, W2-relocated to the artefact surface.

B-1 judge finding F1 (MEDIUM, reproduced in Chromium), the LIVE cross-cutting clause: the
``esc()`` a surface renders with must escape the single quote, or a node id like
``def:x' onmouseover='<payload>`` breaks out of a single-quoted attribute (``data-node='…'``)
and executes on hover. Fixed at the ROOT: ``esc()`` escapes ``'`` → ``&#39;``.

W2: review_surface.html + projection_viewer.html CONSOLIDATED into the ONE artefact surface,
whose render behaviour lives in the shared module ``static_shared/artefact-panes.mjs`` — and
it renders node/section/version ids into SINGLE-quoted ``data-*`` attributes, the exact F1
sink. This clause re-aims THERE: the module's ``esc`` escapes both quotes, and every
single-quoted attribute interpolation routes through it. (F2 — the review surface's
dismissal-audit mass-revoke overrule guard — was surface-specific adjudication chrome; its
executor-level teeth stay tested at the review_surface.adjudicate layer, and its annotate-mode
UI rides the W2 adjudication-verb follow-up.)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PANES = (Path(__file__).resolve().parents[1] / "src" / "laplace"
          / "web" / "static_shared" / "artefact-panes.mjs").read_text(encoding="utf-8")


# ── F1 (the LIVE XSS clause): the artefact module's esc escapes BOTH quotes ──

def test_artefact_esc_escapes_single_quote():
    """The root fix, on the new surface: the module's ``esc`` escapes ``'`` → ``&#39;``
    (Chromium-safe in a single-quoted attribute), and still escapes ``"`` and ``&``/``<``/``>``."""
    # anchor on the statement-ending ";\n" (a ";" inside a string literal like "&amp;" is
    # followed by a quote, never a newline), so the whole chained-replace body is captured.
    m = re.search(r"const esc = \(s\) =>([\s\S]*?);\s*\n", _PANES)
    assert m, "esc helper not found in artefact-panes.mjs"
    esc_src = m.group(1)
    assert "&#39;" in esc_src, "esc() does not escape the single quote (F1 regression)"
    assert re.search(r"replace\(/'/g", esc_src), "esc() has no single-quote replace"
    assert "&quot;" in esc_src, "esc() dropped double-quote escaping"
    assert "&amp;" in esc_src and "&lt;" in esc_src and "&gt;" in esc_src


def test_every_single_quoted_attribute_interpolation_is_esc_wrapped():
    """The AUDIT (F1): every value interpolated at the START of a SINGLE-quoted attribute
    (``attr='"+FUNC(...)``) goes through ``esc`` — no un-esc'd content reaches a single-quoted
    attribute. The node/version/section-id sinks (data-node / data-id / data-open / data-section)
    are the F1 attack surface and must all be esc-wrapped."""
    sinks = re.findall(r"[A-Za-z-]+='\"\s*\+\s*([A-Za-z_][A-Za-z0-9_]*)\(", _PANES)
    assert sinks, "expected at least the data-node / data-id / data-section sinks"
    non_esc = [fn for fn in sinks if fn != "esc"]
    assert not non_esc, f"single-quoted attribute-value sinks not routed through esc(): {non_esc}"
    # the exact ledger-data sinks are present and esc'd (node ids are the F1 vector)
    assert "data-node='\" + esc(" in _PANES, "the node chip sink changed shape"
    assert "data-section='\" + esc(" in _PANES, "the anchor section sink changed shape"
