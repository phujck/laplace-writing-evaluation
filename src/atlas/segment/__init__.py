"""segment - the registry, the size dials, and the one entry point that enforces the laws.

Routing is by extension, in registry order, with the raw-window fallback last. ``segment_bytes``
is the only way spans should be produced outside a unit test: it runs the segmenter and then
runs all three laws over what came back, so a segmenter cannot ship a partition with a hole in
it by forgetting to check.

The dials. ``HARD_CAP_TOKENS`` is 512 because that is the bge-small window: a span past it is
truncated by the encoder, which is exactly the silent loss the cap law exists to make loud. The
target is what the sweep measures (``atlas.tools.segment_sweep`` at 256 / 384 / 512); the
default of 384 is a starting point, and Phase 1's job is to replace it with a measured choice.
"""

from __future__ import annotations

from ..schema import SnapshotNode
from .base import (
    Segmenter,
    SegmentResult,
    check_cap,
    check_coverage,
    check_nesting,
    check_structure,
    est_tokens,
)
from .code import CodeSegmenter
from .fallback import FallbackSegmenter
from .markdown import MarkdownSegmenter
from .structured import JsonlSegmenter, JsonSegmenter, YamlSegmenter
from .tex import TexSegmenter, check_tex_structure

SEGMENTATION_RECIPE_VERSION = "seg/1"

DEFAULT_TARGET_TOKENS = 384
HARD_CAP_TOKENS = 512
SWEEP_TARGETS = (256, 384, 512)

#: Order matters: the first segmenter that claims a path wins, and the fallback claims everything.
ROUTES: tuple[Segmenter, ...] = (
    MarkdownSegmenter(),
    CodeSegmenter(),
    JsonSegmenter(),
    JsonlSegmenter(),
    YamlSegmenter(),
    TexSegmenter(),
)
FALLBACK = FallbackSegmenter()

REGISTRY: dict[str, Segmenter] = {s.segmenter_id: s for s in ROUTES + (FALLBACK,)}


def segmenter_for(path: str) -> Segmenter:
    """The segmenter that claims this path. Never raises: the fallback claims what is left."""
    for seg in ROUTES:
        if seg.can_handle(path):
            return seg
    return FALLBACK


def segment_bytes(node_id: str, path: str, source_content_hash: str, data: bytes,
                  target_tokens: int = DEFAULT_TARGET_TOKENS,
                  hard_cap_tokens: int = HARD_CAP_TOKENS) -> SegmentResult:
    """Segment one source and enforce coverage, cap, structure and nesting on the result."""
    seg = segmenter_for(path)
    result = seg.segment(node_id, path, source_content_hash, data, target_tokens,
                         hard_cap_tokens)
    check_coverage(node_id, len(data), result.spans)
    check_structure(path, result.spans)
    if path.lower().endswith(".tex"):
        check_tex_structure(path, result.spans)
    check_nesting(node_id, result.spans)
    result.oversize = check_cap(node_id, result.spans, hard_cap_tokens)
    return result


def segment_node(node: SnapshotNode, data: bytes,
                 target_tokens: int = DEFAULT_TARGET_TOKENS,
                 hard_cap_tokens: int = HARD_CAP_TOKENS) -> SegmentResult:
    """Segment a snapshot node. Sealed nodes are never segmented - they carry no bytes."""
    if node.sealed:
        return SegmentResult()
    return segment_bytes(node.node_id, node.path, node.content_hash, data,
                         target_tokens, hard_cap_tokens)


__all__ = [
    "DEFAULT_TARGET_TOKENS", "FALLBACK", "HARD_CAP_TOKENS", "REGISTRY", "ROUTES",
    "SEGMENTATION_RECIPE_VERSION", "SWEEP_TARGETS", "SegmentResult", "Segmenter",
    "check_cap", "check_coverage", "check_nesting", "check_structure", "est_tokens",
    "segment_bytes", "segment_node", "segmenter_for",
]
