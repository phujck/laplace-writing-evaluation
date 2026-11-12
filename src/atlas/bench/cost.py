"""cost.py - five cost dimensions, never summed, and the wrappers that COUNT two of them.

Design §6 and seam J7. A single "cost" number is how a fold bill hides inside a query-time win,
so cost here is five separate dimensions and nothing in this module adds them together:

    fold                      wall seconds, model calls, model tokens, vectors built, bytes stored
    fold_amortized_per_query  the fold divided by a STATED reference query count
    query_model_calls         COUNTED by a wrapper, never taken from the arm's declaration
    tokens_touched            COUNTED by a reading wrapper on every span an arm serves
    latency                   median and p95 milliseconds, separately

Correctness is not a cost dimension and is not in this module. It is computed first, by
``scoring.score``, and every aggregate here is taken over correct tasks only.

The two wrappers are the point of the file. ``SpanReader`` is the ONLY way an arm turns a span
into text at query time, and it counts the bytes as they pass; an arm that wants to read without
being counted has to not read. ``ModelCounter`` is the only way an arm calls a model, and the
runner asserts the counted number equals the number the arm's protocol DECLARED - a declared zero
that is actually one is ``ProtocolViolation``, which is the whole mechanism behind the claim that
the Tier-1 arms make no model calls at query time.

``scan_bytes`` is reported and never summed into ``tokens_touched``. The v1 skilled-grep arm was
measured at its best case: the pattern-frequency probes that model a human choosing a distinctive
keyword were not charged, and the caveat said so. Porting that faithfully means the scan is
visible as its own number rather than either hidden or silently folded into the arm's bill.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..errors import ProtocolViolation, UniverseViolation
from ..schema import Span
from .universe import SnapshotView

#: tokens = utf-8 bytes / 4, the repo's canonical estimate and v1's exact definition. Integer
#: division, as v1 did it, so a v1 number and a v2 number are the same kind of number.
BYTES_PER_TOKEN = 4


def tokens_of(text: str) -> int:
    return len(text.encode("utf-8")) // BYTES_PER_TOKEN


def tokens_of_bytes(n: int) -> int:
    return n // BYTES_PER_TOKEN


class SpanReader:
    """The counting wrapper. Every byte an arm serves into a scoring context passes through here.

    Three read verbs, each counted differently because they mean different things:

      ``read_span``       one leaf span - the unit of retrieval. Counts bytes and spans.
      ``read_node``       a whole file - the escape event. Counts bytes and increments the
                          whole-file counter the protocol caps.
      ``scan``            bytes an arm looked at without serving them (the grep pass). Counted
                          into ``scan_bytes`` and NEVER into ``tokens_touched``.

    The reader also enforces the protocol's read caps: past ``max_spans_read``,
    ``max_whole_file_reads`` or ``read_budget_bytes`` it refuses by name. An arm that quietly
    read deeper than it declared and won on spend is seam J6, and this is where it is stopped.
    """

    def __init__(self, view: SnapshotView, max_spans_read: int | None = None,
                 max_whole_file_reads: int | None = None,
                 read_budget_bytes: int | None = None) -> None:
        self.view = view
        self.max_spans_read = max_spans_read
        self.max_whole_file_reads = max_whole_file_reads
        self.read_budget_bytes = read_budget_bytes
        self.bytes_served = 0
        self.spans_read = 0
        self.whole_file_reads = 0
        self.scan_bytes = 0

    # --- the counted reads ------------------------------------------------

    def read_span(self, span: Span) -> str:
        if self.max_spans_read is not None and self.spans_read >= self.max_spans_read:
            raise ProtocolViolation("arm exceeded its declared span-read budget",
                                    max_spans_read=self.max_spans_read, spans_read=self.spans_read)
        text = self.view.span_text(span)
        self._charge(text)
        self.spans_read += 1
        return text

    def read_node(self, node_id: str) -> str:
        if (self.max_whole_file_reads is not None
                and self.whole_file_reads >= self.max_whole_file_reads):
            raise ProtocolViolation("arm exceeded its declared whole-file read budget",
                                    max_whole_file_reads=self.max_whole_file_reads,
                                    whole_file_reads=self.whole_file_reads, node_id=node_id)
        text = self.view.node_text(node_id)
        self._charge(text)
        self.whole_file_reads += 1
        return text

    def read_node_excerpt(self, node_id: str, excerpt: str) -> str:
        """A whole-file OPEN that serves only part of the file into context.

        The v1 flat arm opened the whole diary and put only its last five entries in context; it
        was charged the five entries, and the caveat named the open. Both halves are recorded here:
        the excerpt is charged as served bytes, the file's full size is recorded as ``scan_bytes``
        (reported, never summed), and the open counts against ``max_whole_file_reads``.
        """
        if (self.max_whole_file_reads is not None
                and self.whole_file_reads >= self.max_whole_file_reads):
            raise ProtocolViolation("arm exceeded its declared whole-file read budget",
                                    max_whole_file_reads=self.max_whole_file_reads,
                                    whole_file_reads=self.whole_file_reads, node_id=node_id)
        whole = self.view.node_text(node_id)
        self.scan(max(0, len(whole.encode("utf-8")) - len(excerpt.encode("utf-8"))))
        self._charge(excerpt)
        self.whole_file_reads += 1
        return excerpt

    def read_text(self, text: str, label: str = "") -> str:
        """Charge a string an arm assembled itself (a grep output block). Bytes count, no span."""
        self._charge(text)
        return text

    def scan(self, n_bytes: int) -> None:
        """Bytes looked at but not served. Reported beside the bill, never inside it."""
        self.scan_bytes += n_bytes

    def _charge(self, text: str) -> None:
        n = len(text.encode("utf-8"))
        if (self.read_budget_bytes is not None
                and self.bytes_served + n > self.read_budget_bytes):
            raise ProtocolViolation("arm exceeded its declared read byte budget",
                                    read_budget_bytes=self.read_budget_bytes,
                                    already=self.bytes_served, wanted=n)
        self.bytes_served += n

    # --- what the runner reads off it -------------------------------------

    @property
    def tokens_touched(self) -> int:
        return tokens_of_bytes(self.bytes_served)

    def snapshot_counters(self) -> dict[str, int]:
        return {
            "bytes_served": self.bytes_served,
            "tokens_touched": self.tokens_touched,
            "spans_read": self.spans_read,
            "whole_file_reads": self.whole_file_reads,
            "scan_bytes": self.scan_bytes,
        }


class ModelCounter:
    """The only way an arm may call a model at query time, so the count is observed not claimed."""

    def __init__(self, arm_id: str) -> None:
        self.arm_id = arm_id
        self.calls = 0
        self.tokens = 0

    def call(self, fn: Callable[..., Any], *args: Any, tokens: int = 0, **kwargs: Any) -> Any:
        self.calls += 1
        self.tokens += tokens
        return fn(*args, **kwargs)

    def assert_declared(self, declared: int) -> None:
        if self.calls != declared:
            raise ProtocolViolation(
                "declared query model calls disagree with the counted observation",
                arm=self.arm_id, declared=declared, counted=self.calls,
            )


@dataclass
class FoldCost:
    """What an arm paid ONCE, before any query. Five fields, none of them a total.

    ``wall_seconds`` IS THE BILL: the seconds that built the index this run served, cumulative
    across the calls that built it, NOT the seconds this invocation happened to spend. The
    distinction is seam J7 in one field. An arm whose fold was cached from an earlier run spends
    a fraction of a second reloading it, and reporting that fraction as its fold cost is exactly
    how a fold bill hides inside a query-time win. ``wall_seconds_this_call`` records what this
    invocation spent, and ``cached`` says whether it built anything - so both numbers are present
    and neither can be mistaken for the other.
    """

    wall_seconds: float = 0.0
    wall_seconds_this_call: float = 0.0
    model_calls: int = 0
    model_tokens: int = 0
    vectors_built: int = 0
    bytes_stored: int = 0
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "wall_seconds": round(self.wall_seconds, 4),
            "wall_seconds_this_call": round(self.wall_seconds_this_call, 4),
            "model_calls": self.model_calls,
            "model_tokens": self.model_tokens, "vectors_built": self.vectors_built,
            "bytes_stored": self.bytes_stored, "cached": self.cached,
        }

    def amortized(self, reference_query_count: int) -> dict[str, Any]:
        """The fold divided by a STATED number of queries. The reference count travels with it -
        an amortized number without its denominator is not a number."""
        if reference_query_count <= 0:
            raise ProtocolViolation("amortization needs a positive reference query count",
                                    reference_query_count=reference_query_count)
        n = reference_query_count
        return {
            "reference_query_count": n,
            "wall_seconds_per_query": round(self.wall_seconds / n, 6),
            "model_calls_per_query": round(self.model_calls / n, 6),
            "model_tokens_per_query": round(self.model_tokens / n, 6),
            "bytes_stored_per_query": round(self.bytes_stored / n, 3),
        }


@dataclass
class ArmCost:
    """The five dimensions of one arm over one run. Nothing here is ever summed across them."""

    arm_id: str
    fold: FoldCost = field(default_factory=FoldCost)
    fold_reference_query_count: int = 1
    query_model_calls: int = 0
    query_model_tokens: int = 0
    tokens_touched_median: int | None = None
    tokens_touched_total: int = 0
    scan_bytes_total: int = 0
    latency_median_ms: float | None = None
    latency_p95_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm_id,
            "fold": self.fold.to_dict(),
            "fold_amortized_per_query": self.fold.amortized(self.fold_reference_query_count),
            "query_model_calls": self.query_model_calls,
            "query_model_tokens": self.query_model_tokens,
            "tokens_touched": {
                "median": self.tokens_touched_median, "total": self.tokens_touched_total,
            },
            "scan_bytes_total_uncharged": self.scan_bytes_total,
            "latency_ms": {"median": self.latency_median_ms, "p95": self.latency_p95_ms},
        }


def median(xs: list[float]) -> float | None:
    """v1's median: sort, take the upper-middle element. Kept identical so numbers compare."""
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def percentile(xs: list[float], q: float) -> float | None:
    """Nearest-rank percentile - no interpolation, so the value returned is one that occurred."""
    if not xs:
        return None
    ordered = sorted(xs)
    idx = int(round(q * (len(ordered) - 1)))
    return ordered[max(0, min(idx, len(ordered) - 1))]


def guard_view(view: SnapshotView, node_id: str) -> None:
    """Refuse a node outside the view before an arm builds anything on it."""
    if not view.has_node(node_id):
        raise UniverseViolation("node is outside the declared view",
                                node_id=node_id, universe=view.universe.name)
