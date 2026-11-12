"""fallback.py - bounded raw windows, for sources with no structure this layer can read.

Reaching this segmenter is itself a measurement. Every node it cuts emits a segmentation-miss
event naming the extension, so "how much of the corpus has no structural reader" is a number the
sweep prints rather than an impression. A structured source arriving here is a STRUCTURE-law
violation and is caught by ``base.check_structure``.

Windows prefer line boundaries where the source has them and fall back to fixed byte offsets
where it does not, so this segmenter never produces an oversize span.

On overlap: leaf spans MUST partition (the coverage law), so the emitted ranges do not overlap.
The overlap the design asks for travels as ``meta.context_start`` - the offset a reader should
start at to materialize the window with its preceding context. That keeps both properties: a
reader gets overlap, and coverage stays a well-defined number instead of a sum over
double-counted bytes.
"""

from __future__ import annotations

from .base import RawSpan, SegmentResult, finalize, split_block, tokens_to_bytes

REFINE_SEPS = (b"\n\n", b"\n")
LEAF_KIND = "raw_window"

#: Context a reader may prepend to a window. Not part of the span's own range.
OVERLAP_TOKENS = 32


class FallbackSegmenter:
    segmenter_id = "fallback/1"
    version = "seg/1"

    def can_handle(self, path: str) -> bool:
        return True                     # the last route; the registry tries it last

    def segment(self, node_id: str, path: str, source_content_hash: str, data: bytes,
                target_tokens: int, hard_cap_tokens: int) -> SegmentResult:
        if not data:
            return SegmentResult()
        target_bytes = tokens_to_bytes(target_tokens)
        cap_bytes = tokens_to_bytes(hard_cap_tokens)
        overlap_bytes = tokens_to_bytes(OVERLAP_TOKENS)

        tiles: list[tuple[int, int]] = []
        for a, b in split_block(data, 0, len(data), target_bytes, cap_bytes, REFINE_SEPS):
            if b - a <= cap_bytes:
                tiles.append((a, b))
                continue
            # No usable line boundary: cut at fixed offsets. This is the one place a cut is
            # made without regard to content, and it is why arriving here is recorded as a miss.
            pos = a
            while pos < b:
                tiles.append((pos, min(pos + target_bytes, b)))
                pos += target_bytes

        raws = [
            RawSpan(a, b, True, LEAF_KIND, [], {"context_start": max(0, a - overlap_bytes)})
            for a, b in tiles
        ]
        result = finalize(node_id, source_content_hash, self.segmenter_id, self.version,
                          raws, hard_cap_tokens, oversize_reason="raw-window-over-cap")
        ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""
        result.misses.append({
            "node_id": node_id, "path": path, "segmenter_id": self.segmenter_id,
            "reason": "segmentation-miss/no-structural-reader",
            "detail": {"extension": ext, "windows": len(tiles)},
        })
        return result
