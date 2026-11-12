"""test_chrome_tour_walk.py — the tour must walk every rostered surface's real room.

The '? tour' (shell.js) leads with two shared-chrome steps (TOUR_SHARED: the journey
spine + the context header) and then walks the CURRENT surface via a per-route table
(TOUR_ROUTES, keyed by the roster view id = activeView()). A route that drifts from the
live DOM degrades — every step skips — and the tour silently collapses back to the two
shared steps (the "chrome-only stub" the chrome audit named on storyboard/conceptric/
assets/Machine).

This is the DURABLE half of the walk assertion: it proves the authored table still
carries a per-surface room for EVERY rostered surface, so a pane rename that re-stubs a
tour is caught here even without a browser. The live half (each surface's tour yields
more than the 2 shared steps against the real DOM) rides the playwright walk, which reads
HymnShell.tourStepCount().
"""
from __future__ import annotations

import re
from pathlib import Path

from laplace.web import shared_ui

_SHELL = Path(shared_ui.__file__).resolve().parent / "static_shared" / "shell.js"


def _shell_text() -> str:
    return _SHELL.read_text(encoding="utf-8")


def _block(text: str, opener: str) -> str:
    """The text of a `const NAME = [` / `= {` literal, from its opener to the line that
    closes it at the base indentation (`  ];` / `  };`)."""
    start = text.index(opener)
    tail = text[start:]
    m = re.search(r"\n  \];\n", tail) if opener.endswith("[") else re.search(r"\n  \};\n", tail)
    assert m, f"could not bound the block for {opener!r}"
    return tail[: m.end()]


def _shared_steps() -> int:
    block = _block(_shell_text(), "const TOUR_SHARED = [")
    return len(re.findall(r"\{\s*selector:", block))


def _route_steps() -> dict[str, int]:
    block = _block(_shell_text(), "const TOUR_ROUTES = {")
    # top-level route keys sit at four-space indent as `    <id>: [`
    routes: dict[str, int] = {}
    for m in re.finditer(r"\n    ([A-Za-z_][\w]*): \[", block):
        rid = m.group(1)
        # the route's own steps: `{ selector:` up to the next top-level key or the block end
        seg_start = m.end()
        nxt = re.search(r"\n    [A-Za-z_][\w]*: \[", block[seg_start:])
        seg = block[seg_start: seg_start + nxt.start()] if nxt else block[seg_start:]
        routes[rid] = len(re.findall(r"\{\s*selector:", seg))
    return routes


def test_tour_shared_is_exactly_two_steps():
    """The shared baseline the walk assertion compares against is TWO steps (the journey
    spine + the context header). A surface tour must exceed this; if the shared block
    itself grows, the '> 2' contract must be re-derived deliberately, not silently."""
    assert _shared_steps() == 2, (
        f"TOUR_SHARED is {_shared_steps()} steps, not 2 — the walk assertion's baseline "
        "moved; re-derive the per-surface '> shared' contract before changing this."
    )


def test_every_rostered_surface_has_a_real_tour_room():
    """Every rostered surface carries a per-route table with at least two surface-specific
    steps, so the authored tour walks the room rather than collapsing to the chrome. The
    Machine row (view id 'pipeline', served at /project) is covered like any other."""
    routes = _route_steps()
    roster_ids = [v["id"] for v in shared_ui._VIEWS]
    stubbed = [rid for rid in roster_ids if routes.get(rid, 0) < 2]
    assert not stubbed, (
        "rostered surfaces whose '? tour' is a stub (< 2 surface steps → would collapse to "
        f"the 2 shared chrome steps): {stubbed}. Re-point TOUR_ROUTES[<id>] at the live DOM."
    )
