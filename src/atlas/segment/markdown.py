"""markdown.py - spans by heading trail: merge undersized sections, split oversized ones.

The heading chain IS the structural trail. A section that fits the target becomes one leaf span
carrying its trail; a section too large is cut at its subsections, and if it has none, at
paragraph boundaries (then line boundaries - see ``base.split_block``). A section that ends up
split into two or more leaves also emits a non-leaf parent span over its whole range, which is
what makes a big document tree depth instead of vector overload.

Headings inside fenced code blocks are not headings. A repo whose markdown is full of ``` fences
would otherwise cut at every commented ``#`` line and produce trails naming shell comments.
"""

from __future__ import annotations

import re

from .base import Heading, RawSpan, SegmentResult, finalize, structural_spans

_HEADING_RE = re.compile(rb"(?m)^(#{1,6})[ \t]+(.*)$")
_FENCE_RE = re.compile(rb"(?m)^(?:```|~~~)")

REFINE_SEPS = (b"\n\n", b"\n")
LEAF_KIND = "md_block"
PARENT_KIND = "md_section"


def _fenced_regions(data: bytes) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    open_at: int | None = None
    for m in _FENCE_RE.finditer(data):
        if open_at is None:
            open_at = m.start()
        else:
            regions.append((open_at, m.end()))
            open_at = None
    if open_at is not None:
        regions.append((open_at, len(data)))
    return regions


def headings_of(data: bytes) -> list[Heading]:
    fences = _fenced_regions(data)
    out: list[Heading] = []
    for m in _HEADING_RE.finditer(data):
        off = m.start()
        if any(a <= off < b for a, b in fences):
            continue
        title = m.group(2).decode("utf-8", errors="replace").strip().rstrip("#").strip()
        out.append(Heading(offset=off, level=len(m.group(1)), title=title[:120]))
    return out


class MarkdownSegmenter:
    segmenter_id = "markdown/1"
    version = "seg/2"
    extensions = (".md", ".markdown")

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
        return finalize(node_id, source_content_hash, self.segmenter_id, self.version,
                        raws, hard_cap_tokens,
                        oversize_reason="markdown-block-has-no-paragraph-or-line-break")
