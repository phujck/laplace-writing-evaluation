"""tex.py - spans by sectioning command, nested chapter > section > subsection.

Same shape as markdown: the sectioning chain is the trail, small sections merge, large ones
split at their subsections and then at paragraph boundaries. Only the marker syntax differs.

``\\input`` and ``\\include`` are NOT followed. A span addresses bytes of one immutable source;
resolving an input would put another node's bytes inside this node's range and break the
partition. The include graph is an edge, and edges are Phase 6.
"""

from __future__ import annotations

import re

from .base import Heading, RawSpan, SegmentResult, finalize, structural_spans
from ..errors import StructureViolation

_SECTION_RE = re.compile(
    rb"(?m)^\\(part|chapter|section|subsection|subsubsection|paragraph)\*?\{([^}]*)\}"
)
_LEVELS = {b"part": 1, b"chapter": 2, b"section": 3, b"subsection": 4,
           b"subsubsection": 5, b"paragraph": 6}

REFINE_SEPS = (b"\n\n", b"\n")
LEAF_KIND = "tex_block"
PARENT_KIND = "tex_section"


def headings_of(data: bytes) -> list[Heading]:
    out: list[Heading] = []
    for m in _SECTION_RE.finditer(data):
        level = _LEVELS.get(m.group(1), 6)
        title = m.group(2).decode("utf-8", errors="replace").strip()
        out.append(Heading(offset=m.start(), level=level, title=title[:120]))
    return out


class TexSegmenter:
    segmenter_id = "tex/1"
    version = "seg/3"
    extensions = (".tex",)

    def can_handle(self, path: str) -> bool:
        return path.lower().endswith(self.extensions)

    def segment(self, node_id: str, path: str, source_content_hash: str, data: bytes,
                target_tokens: int, hard_cap_tokens: int) -> SegmentResult:
        if not data:
            return SegmentResult()
        raws: list[RawSpan] = structural_spans(
            data, 0, len(data), headings_of(data), target_tokens, hard_cap_tokens,
            LEAF_KIND, PARENT_KIND, REFINE_SEPS,
        )
        # Paragraph refinement can isolate a delimiter-only tail. Keep those bytes
        # with an adjacent sibling so every encoded leaf contains source content.
        leaves = sorted((raw for raw in raws if raw.is_leaf), key=lambda raw: raw.start)
        for index, raw in enumerate(leaves):
            if data[raw.start:raw.end].strip():
                continue
            previous = next((item for item in reversed(leaves[:index])
                             if item in raws and item.end == raw.start
                             and item.parent_range == raw.parent_range), None)
            following = next((item for item in leaves[index + 1:]
                              if item in raws and item.start == raw.end
                              and item.parent_range == raw.parent_range), None)
            if previous is not None:
                previous.end = raw.end
                raws.remove(raw)
            elif following is not None:
                following.start = raw.start
                raws.remove(raw)
        return finalize(node_id, source_content_hash, self.segmenter_id, self.version,
                        raws, hard_cap_tokens,
                        oversize_reason="tex-block-has-no-paragraph-or-line-break")


def check_tex_structure(path: str, spans: list) -> None:
    """TeX must retain its structural segmenter, never a raw-window fallback."""
    for span in spans:
        if span.segmenter_id != TexSegmenter.segmenter_id or span.kind not in {LEAF_KIND, PARENT_KIND}:
            raise StructureViolation("TeX source lost its structural segmenter", path=path,
                                     span_id=span.span_id, segmenter_id=span.segmenter_id)
