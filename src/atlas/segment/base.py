"""base.py - the Segmenter contract, the shared cutting machinery, and the three laws.

The unit of retrieval is a span, never a file (design §5, the author's mid-design requirement).
Three laws bind every segmenter, and each is a property checked mechanically here rather than a
claim made in a docstring:

  COVERAGE   leaf spans partition every unsealed text node's bytes, exactly - offset 0 to
             size_bytes with no gap and no overlap. Silent truncation (the 480-character
             recipe representing a 7 KB median file) becomes structurally impossible rather
             than merely discouraged.
  CAP        no leaf span exceeds ``hard_cap_tokens``. A source that cannot be split at any
             boundary the segmenter knows is counted in ``oversize_spans`` and carries
             ``meta.oversize_reason`` - named, never silently sliced and never silently kept.
  STRUCTURE  a structured source never reaches the raw-window fallback. JSON and JSONL bind
             strictly; YAML binds to a bounded top-level-key scan (see structured.py).

Coverage is not asserted after the fact - it is built in. Every segmenter chooses CUT POINTS
inside a range and this module tiles the range at them (``pack_cuts``), so the partition holds
by construction and the check is a regression test rather than the mechanism.

The size dials are token estimates, and the estimate is bytes/4 rounded up - the repo's
canonical figure (``src/laplace/storyboard.py:1131``). ``hard_cap_tokens`` defaults to the
bge-small window (512): a span past it is truncated by the encoder, which is the silent loss
the cap law exists to make loud.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..errors import CapViolation, CoverageViolation, NestingViolation, StructureViolation
from ..schema import Span

# Extensions that must never reach the raw fallback. json/jsonl are strict (a real parse of the
# structure); yaml/yml bind to the bounded line scan, which is honest structure-awareness
# without a parser - pyyaml is not an atlas runtime dependency.
STRUCTURED_EXTS = (".json", ".jsonl", ".yaml", ".yml")

BYTES_PER_TOKEN = 4


def est_tokens(n_bytes: int) -> int:
    """bytes/4, rounded up. Rounding up keeps a nonempty span from estimating zero tokens."""
    if n_bytes <= 0:
        return 0
    return -(-n_bytes // BYTES_PER_TOKEN)


def tokens_to_bytes(n_tokens: int) -> int:
    return n_tokens * BYTES_PER_TOKEN


# ---------------------------------------------------------------------------
# the intermediate span, before ids
# ---------------------------------------------------------------------------

@dataclass
class RawSpan:
    """A cut, before it becomes a Span. ``parent_range`` names the parent by its byte range.

    Parents are identified by range rather than by index because a range is unique per node
    among the spans this layer emits: a parent span is emitted only when it covers two or more
    leaves, so it can never coincide with a leaf, and two distinct parents cover distinct
    ranges.
    """

    start: int
    end: int
    is_leaf: bool
    kind: str
    trail: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    parent_range: tuple[int, int] | None = None


@dataclass
class SegmentResult:
    """What one segmenter returns for one node: the spans, plus what it could not do."""

    spans: list[Span] = field(default_factory=list)
    misses: list[dict[str, Any]] = field(default_factory=list)
    oversize: list[dict[str, Any]] = field(default_factory=list)


@runtime_checkable
class Segmenter(Protocol):
    """The contract. ``segment`` receives raw bytes and returns spans over those same bytes."""

    segmenter_id: str
    version: str

    def can_handle(self, path: str) -> bool:
        ...

    def segment(self, node_id: str, path: str, source_content_hash: str, data: bytes,
                target_tokens: int, hard_cap_tokens: int) -> SegmentResult:
        ...


# ---------------------------------------------------------------------------
# cutting - the machinery every segmenter shares
# ---------------------------------------------------------------------------

def pack_cuts(start: int, end: int, cuts: list[int], target_bytes: int) -> list[tuple[int, int]]:
    """Tile ``[start, end)`` at a subset of ``cuts``, merging units up to ``target_bytes``.

    This is both the merge and the partition. Dropping a cut merges two units; keeping one
    splits. Units already larger than the target become their own tile and are handed to the
    caller's refinement. The walk always advances, so the tiles cover the range exactly once.
    """
    bounds = [start] + sorted({c for c in cuts if start < c < end}) + [end]
    tiles: list[tuple[int, int]] = []
    i = 0
    while i < len(bounds) - 1:
        j = i + 1
        while j < len(bounds) - 1 and bounds[j + 1] - bounds[i] <= target_bytes:
            j += 1
        tiles.append((bounds[i], bounds[j]))
        i = j
    return tiles


def split_block(data: bytes, start: int, end: int, target_bytes: int, cap_bytes: int,
                seps: tuple[bytes, ...]) -> list[tuple[int, int]]:
    """Cut an oversized block at the coarsest separator that helps, then the next finer one.

    ``seps`` is ordered coarse-to-fine - for prose that is paragraph break then line break. The
    design fixes paragraph boundaries as the markdown split point; the line break is the second
    stage, so a 100 KB run of unbroken lines becomes spans instead of one named oversize. A
    block with no separator left is returned whole, and the caller names it oversize.
    """
    if end - start <= cap_bytes:
        return [(start, end)]
    for i, sep in enumerate(seps):
        cuts: list[int] = []
        pos = data.find(sep, start, end)
        while pos != -1:
            cut = pos + len(sep)
            if start < cut < end:
                cuts.append(cut)
            pos = data.find(sep, cut, end)
        if not cuts:
            continue
        tiles = pack_cuts(start, end, cuts, target_bytes)
        if len(tiles) == 1:
            continue
        out: list[tuple[int, int]] = []
        for a, b in tiles:
            if b - a > cap_bytes:
                out.extend(split_block(data, a, b, target_bytes, cap_bytes, seps[i + 1:]))
            else:
                out.append((a, b))
        return out
    return [(start, end)]


@dataclass(frozen=True)
class Heading:
    """One structural marker: where it starts, how deep it sits, what it is called."""

    offset: int
    level: int
    title: str


def structural_spans(data: bytes, start: int, end: int, headings: list[Heading],
                     target_tokens: int, hard_cap_tokens: int, leaf_kind: str,
                     parent_kind: str, refine_seps: tuple[bytes, ...],
                     trail: tuple[str, ...] = ()) -> list[RawSpan]:
    """Tile a range by its structural markers, merging small sections and splitting large ones.

    Shared by markdown (heading trail), tex (sectioning commands) and code (top-level symbols,
    all at one level). The rule at each depth: if the whole range fits the target it is one
    leaf; otherwise cut at the shallowest markers present, pack the units up to the target, and
    recurse into any single unit still over target. A unit that splits into two or more leaves
    also emits a non-leaf parent span over its own range, which is how a heading section
    becomes a coarse node over its subsections.
    """
    target_bytes = tokens_to_bytes(target_tokens)
    cap_bytes = tokens_to_bytes(hard_cap_tokens)

    def emit(a: int, b: int, inner: list[Heading], trail_here: tuple[str, ...]) -> list[RawSpan]:
        if b <= a:
            return []
        own = [heading for heading in inner if heading.offset == a]
        if own:
            own_head = min(own, key=lambda heading: (heading.level, heading.title))
            if not trail_here or trail_here[-1] != own_head.title:
                trail_here = trail_here + (own_head.title,)
        if b - a <= target_bytes:
            return [RawSpan(a, b, True, leaf_kind, list(trail_here))]
        tops: list[Heading] = []
        descendants = [heading for heading in inner if a < heading.offset < b]
        if descendants:
            min_level = min(h.level for h in descendants)
            tops = [h for h in descendants if h.level == min_level]
        if not tops:
            return [RawSpan(ta, tb, True, leaf_kind, list(trail_here))
                    for ta, tb in split_block(data, a, b, target_bytes, cap_bytes, refine_seps)]

        bounds = [a] + [h.offset for h in tops] + [b]
        units = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
        head_at = {h.offset: h for h in tops}

        out: list[RawSpan] = []
        i = 0
        while i < len(units):
            j = i
            size = units[i][1] - units[i][0]
            while j + 1 < len(units) and size + (units[j + 1][1] - units[j + 1][0]) <= target_bytes:
                j += 1
                size += units[j][1] - units[j][0]
            ta, tb = units[i][0], units[j][1]
            head = head_at.get(ta)
            sub_trail = trail_here + (head.title,) if head else trail_here
            if i == j and tb - ta > target_bytes:
                nested = [h for h in inner if ta < h.offset < tb]
                children = emit(ta, tb, nested, sub_trail)
                if len(children) >= 2:
                    for child in children:
                        if child.parent_range is None:
                            child.parent_range = (ta, tb)
                    out.append(RawSpan(ta, tb, False, parent_kind, list(sub_trail)))
                out.extend(children)
            else:
                out.append(RawSpan(ta, tb, True, leaf_kind, list(sub_trail)))
            i = j + 1
        return out

    return emit(start, end, [h for h in headings if start <= h.offset < end], trail)


# ---------------------------------------------------------------------------
# finalization - raw cuts become Spans with ids, and the cap law is applied
# ---------------------------------------------------------------------------

def finalize(node_id: str, source_content_hash: str, segmenter_id: str, seg_version: str,
             raws: list[RawSpan], hard_cap_tokens: int,
             oversize_reason: str = "no-boundary-under-cap") -> SegmentResult:
    """Turn raw cuts into Spans: stable ordering, ids, parent links, oversize naming.

    Ordering is deterministic and independent of the order the segmenter produced cuts in:
    by start offset, then widest first (so a parent precedes its children), then leaves last.
    """
    raws = sorted(raws, key=lambda r: (r.start, -(r.end - r.start), 1 if r.is_leaf else 0))
    result = SegmentResult()
    cap = hard_cap_tokens
    for raw in raws:
        tokens = est_tokens(raw.end - raw.start)
        meta = dict(raw.meta)
        if raw.is_leaf and tokens > cap and "oversize_reason" not in meta:
            meta["oversize_reason"] = oversize_reason
        span_id = Span.compute_id(source_content_hash, raw.start, raw.end,
                                  segmenter_id, seg_version)
        parent_id = None
        if raw.parent_range is not None:
            parent_id = Span.compute_id(source_content_hash, raw.parent_range[0],
                                        raw.parent_range[1], segmenter_id, seg_version)
        span = Span(
            span_id=span_id, node_id=node_id, source_content_hash=source_content_hash,
            segmenter_id=segmenter_id, seg_version=seg_version, start=raw.start, end=raw.end,
            est_tokens=tokens, is_leaf=raw.is_leaf, parent_span=parent_id, kind=raw.kind,
            trail=list(raw.trail), meta=meta,
        )
        result.spans.append(span)
        if raw.is_leaf and tokens > cap:
            result.oversize.append({
                "node_id": node_id, "span_id": span_id, "start": raw.start, "end": raw.end,
                "est_tokens": tokens, "segmenter_id": segmenter_id,
                "reason": meta["oversize_reason"], "trail": list(raw.trail),
            })
    return result


# ---------------------------------------------------------------------------
# the laws, as checks
# ---------------------------------------------------------------------------

def check_coverage(node_id: str, node_size: int, spans: list[Span]) -> int:
    """COVERAGE: leaf spans tile [0, node_size) exactly. Returns the covered byte count."""
    leaves = sorted((s for s in spans if s.is_leaf), key=lambda s: (s.start, s.end))
    pos = 0
    for span in leaves:
        if span.start != pos:
            raise CoverageViolation(
                "leaf spans do not partition the node",
                node_id=node_id, expected_start=pos, got=span.start, span_id=span.span_id,
            )
        if span.end < span.start:
            raise CoverageViolation("leaf span ends before it starts", node_id=node_id,
                                    span_id=span.span_id)
        pos = span.end
    if pos != node_size:
        raise CoverageViolation("leaf spans do not cover the node", node_id=node_id,
                                covered=pos, size=node_size)
    return pos


def check_cap(node_id: str, spans: list[Span], hard_cap_tokens: int) -> list[dict[str, Any]]:
    """CAP: an over-cap leaf is legal only when it names why it could not be split."""
    over: list[dict[str, Any]] = []
    for span in spans:
        if not span.is_leaf or span.est_tokens <= hard_cap_tokens:
            continue
        reason = span.meta.get("oversize_reason")
        if not reason:
            raise CapViolation("leaf span exceeds the hard cap without a named reason",
                               node_id=node_id, span_id=span.span_id,
                               est_tokens=span.est_tokens, cap=hard_cap_tokens)
        # The trail and the byte range travel with the count: the Phase 1 gate is coverage 1.0
        # with each oversize span INDIVIDUALLY explainable, and a bare count explains nothing.
        over.append({"node_id": node_id, "span_id": span.span_id, "kind": span.kind,
                     "start": span.start, "end": span.end, "est_tokens": span.est_tokens,
                     "reason": reason, "trail": list(span.trail)})
    return over


def check_structure(path: str, spans: list[Span], fallback_prefix: str = "fallback") -> None:
    """STRUCTURE: a structured source never reaches the raw-window fallback."""
    lowered = path.lower()
    if not lowered.endswith(STRUCTURED_EXTS):
        return
    for span in spans:
        if span.segmenter_id.startswith(fallback_prefix):
            raise StructureViolation("a structured source was cut by the raw fallback",
                                     path=path, span_id=span.span_id,
                                     segmenter_id=span.segmenter_id)


def check_nesting(node_id: str, spans: list[Span]) -> None:
    """Every declared parent is present in the same node and contains its child's range."""
    ranges = {s.span_id: (s.start, s.end) for s in spans}
    for span in spans:
        if span.parent_span is None:
            continue
        parent = ranges.get(span.parent_span)
        if parent is None:
            raise NestingViolation("span names a parent that is not in the node",
                                   node_id=node_id, span_id=span.span_id,
                                   parent_span=span.parent_span)
        if span.start < parent[0] or span.end > parent[1]:
            raise NestingViolation("parent span does not contain its child", node_id=node_id,
                                   span_id=span.span_id, child=(span.start, span.end),
                                   parent_range=parent)
