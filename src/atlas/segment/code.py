"""code.py - spans by top-level symbol, with the docstring attached to the symbol it documents.

Cuts fall at column-zero symbol starts, so a function's body, its signature and its docstring
travel as one span: the docstring is inside the symbol's byte range by construction, never a
separate fragment that retrieval can surface without the code it describes. The bytes before
the first symbol (module docstring, imports, constants) are the module-header span.

Decorators bind to the symbol they decorate: the cut is at the first ``@`` line, and the ``def``
or ``class`` line that follows it does not start a new span.

Segmentation is by regex over column-zero lines, not by ``ast``. One code path, no parse-failure
branch, and it works identically on a partial file, a syntax error, and the ``.mjs`` half of the
repo - where the same column-zero rule applies to ``function``/``class``/``const`` at the top
level. A symbol larger than the cap is split at blank-line then line boundaries.
"""

from __future__ import annotations

import re

from .base import Heading, RawSpan, SegmentResult, finalize, structural_spans

_PY_SYMBOL_RE = re.compile(rb"(?m)^(@|async\s+def\s+|def\s+|class\s+)([A-Za-z_][A-Za-z0-9_]*)?")
_JS_SYMBOL_RE = re.compile(
    rb"(?m)^(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    rb"(?:function\s+([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*)"
    rb"|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=)"
)

REFINE_SEPS = (b"\n\n", b"\n")
LEAF_KIND = "code_block"
PARENT_KIND = "code_symbol"

PY_EXT = (".py",)
JS_EXT = (".js", ".mjs", ".ts")


def _python_symbols(data: bytes) -> list[Heading]:
    """Column-zero symbol starts. A decorator opens the block; the def it decorates does not."""
    out: list[Heading] = []
    pending_decorator = False
    for m in _PY_SYMBOL_RE.finditer(data):
        head = m.group(1)
        name = (m.group(2) or b"").decode("utf-8", errors="replace")
        if head == b"@":
            if pending_decorator:
                continue                       # a second decorator on the same symbol
            pending_decorator = True
            out.append(Heading(offset=m.start(), level=1, title=f"@{name}"[:120]))
            continue
        if pending_decorator:
            pending_decorator = False          # this def belongs to the decorator block above
            continue
        out.append(Heading(offset=m.start(), level=1, title=name[:120]))
    return out


def _js_symbols(data: bytes) -> list[Heading]:
    out: list[Heading] = []
    for m in _JS_SYMBOL_RE.finditer(data):
        name = next((g for g in m.groups() if g), b"").decode("utf-8", errors="replace")
        out.append(Heading(offset=m.start(), level=1, title=name[:120]))
    return out


class CodeSegmenter:
    segmenter_id = "code/1"
    version = "seg/2"
    extensions = PY_EXT + JS_EXT

    def can_handle(self, path: str) -> bool:
        return path.lower().endswith(self.extensions)

    def segment(self, node_id: str, path: str, source_content_hash: str, data: bytes,
                target_tokens: int, hard_cap_tokens: int) -> SegmentResult:
        if not data:
            return SegmentResult()
        symbols = _python_symbols(data) if path.lower().endswith(PY_EXT) else _js_symbols(data)
        raws: list[RawSpan] = structural_spans(
            data, 0, len(data), symbols, target_tokens, hard_cap_tokens,
            LEAF_KIND, PARENT_KIND, REFINE_SEPS,
        )
        return finalize(node_id, source_content_hash, self.segmenter_id, self.version,
                        raws, hard_cap_tokens,
                        oversize_reason="code-block-has-no-blank-or-line-break")
