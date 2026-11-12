"""A1 (W8-judge amendment) — THE CHROME ECHOES THE STORE'S LOUDNESS.

``/shared/versions`` carries ``sources.editor_saves.dropped`` (``shared_ui._editor_save_rows``,
fed by ``projection_viewer._prune_editor_saves``'s LOUD ``dropped[]`` ledger) but before this
amendment the rail rendered NOTHING of it — a save could age out of the 32-bound with no
chrome naming where it went.

Banking 33+ real saves to actually cross the bound (so a browser walk could observe the
banner for real) is slow, so this is the unit-level DOM-free alternative the dispatch
offered: the REAL string-building function is extracted from the shipped
``artefact-panes.mjs`` source (brace-matched, the ``tests/test_w3_3_rail.py`` idiom) and
evaluated in a bare Node process — no browser, no DOM, exercising the EXACT shipped logic
rather than a hand-duplicated copy. The end-to-end browser proof lives in
``tests/j4_editor_history.playwright.mjs`` (stubs ``/shared/versions`` for one assertion).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[1]
_PANES = _ROOT / "src" / "laplace" / "web" / "static_shared" / "artefact-panes.mjs"
_NODE = shutil.which("node")


def _panes_source() -> str:
    return _PANES.read_text(encoding="utf-8")


def _brace_body(text: str, sig: str) -> str:
    """The ``{...}`` body of a function found by its signature (brace-matched) — mirrors
    ``tests/test_w3_3_rail.py``'s helper so the extracted snippet is provably the REAL
    shipped source, not a hand-copied stand-in that could silently drift from it."""
    i = text.index(sig)
    b = text.index("{", i)
    depth, k = 0, b
    while k < len(text):
        c = text[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[i:k + 1]
        k += 1
    raise AssertionError(f"unbalanced braces after {sig!r}")


@pytest.mark.skipif(_NODE is None, reason="node not available")
def test_dropped_banner_renders_the_count_and_names_the_store_index(tmp_path):
    src = _panes_source()
    esc_line = next(l for l in src.splitlines() if l.strip().startswith("const esc ="))
    # `esc` is a one-line arrow function whose body continues over further .replace(...)
    # lines — pull the full statement up to its terminating `;`. A naive
    # ``src.index(";", ...)`` lands INSIDE the "&#39;" html-entity text (that literal
    # apostrophe-entity string itself contains a ';' character) rather than the real
    # statement terminator, so anchor on the exact closing call instead.
    start = src.index(esc_line)
    end_marker = "\"&#39;\");"
    end = src.index(end_marker, start) + len(end_marker)
    esc_src = src[start:end]
    info_tag_src = _brace_body(src, "function infoTag(txt)")
    banner_src = _brace_body(src, "function editorDroppedBannerHTML(vers)")

    harness = (
        esc_src + "\n"
        + info_tag_src + "\n"
        + banner_src + "\n"
        + "const out = {\n"
        + "  none: editorDroppedBannerHTML({sources:{editor_saves:{dropped:0}}}),\n"
        + "  absent_sources: editorDroppedBannerHTML({}),\n"
        + "  singular: editorDroppedBannerHTML({sources:{editor_saves:{dropped:1}}}),\n"
        + "  plural: editorDroppedBannerHTML({sources:{editor_saves:{dropped:7}}}),\n"
        + "};\n"
        + "process.stdout.write(JSON.stringify(out));\n"
    )
    js = tmp_path / "banner.mjs"
    js.write_text(harness, encoding="utf-8")
    res = subprocess.run([_NODE, str(js)], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)

    assert out["none"] == "", "zero dropped renders nothing (additive chrome, never noise)"
    assert out["absent_sources"] == "", "a payload with no editor_saves source renders nothing"

    assert "hy-rail-trunc" in out["singular"], "mirrors the 16KB truncated-banner CSS idiom"
    assert "1 older save dropped by the 32-bound" in out["singular"], out["singular"]
    assert "1 older saves" not in out["singular"], "singular count reads grammatically"

    assert "7 older saves dropped by the 32-bound" in out["plural"], out["plural"]
    assert "hy-info" in out["plural"] and "ⓘ" in out["plural"], "the ⓘ info tag is present"
    assert "index.json" in out["plural"], "the ⓘ names the store index"
