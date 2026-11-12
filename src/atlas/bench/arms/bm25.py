"""bm25.py - Okapi BM25 over the view's leaf spans. Pure python, no new dependency.

The lexical retrieval baseline, implemented directly rather than pulled in. A BM25 is forty lines
of arithmetic; a dependency for it would be forty lines of arithmetic plus a version axis nobody
declared, and the atlas runtime is numpy-only by design.

The parameters, stated because an unstated parameter is an unmeasured one:

    k1 = 1.5    term-frequency saturation - the standard Okapi value
    b  = 0.75   length normalisation - the standard Okapi value
    idf = ln(1 + (N - df + 0.5) / (df + 0.5))    the nonnegative (Lucene) form, so a term in
                nearly every span cannot contribute a negative score and push a span DOWN for
                containing a query word

THE TOKENIZER IS THE SCORER'S OWN. Documents and queries are tokenized by running the shared
``normalize`` pipeline - JSON-unescape, strip emphasis, strip digit-group commas, unify dashes,
collapse whitespace, casefold - and then splitting on ``[a-z0-9][a-z0-9_./-]*``. That is the same
character class the v1 skilled-grep arm uses to pick question tokens, so the two lexical arms
share one vocabulary and a difference between them is a difference of method rather than of
tokenization. It also means a path (``src/laplace/wake.py``) and a dotted id survive as single
tokens instead of shattering into fragments.

The fold walks every leaf span in the view once and builds postings. Its bill - wall seconds,
bytes read, zero model calls - is recorded as ``FoldCost`` and reported per query against a
stated reference count; nothing sums it into the query-time number.
"""

from __future__ import annotations

import math
import re
import time
from collections import defaultdict

from ...errors import ArmUnavailable
from ...segment import SEGMENTATION_RECIPE_VERSION
from ..cost import FoldCost, ModelCounter, SpanReader
from ..protocol import NO_MODEL, ArmProtocol
from ..scoring import normalize
from ..task import BenchTask
from ..universe import SnapshotView
from .base import ArmAnswer, BaseArm

K1 = 1.5
B = 0.75
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_./-]*")

#: How many spans the arm serves into context. Ten is v1's descent k, kept so the retrieval arms
#: and the v1 numbers are read at the same depth.
DEFAULT_K = 10
READ_BUDGET_BYTES = 1 * 1024 * 1024


def tokenize(text: str) -> list[str]:
    """The normalize pipeline's casefold word split. One function, documents and queries alike."""
    return TOKEN_RE.findall(normalize(text))


class Bm25Arm(BaseArm):
    """Okapi BM25 over leaf spans, k1=1.5 b=0.75, top-k served through the counting reader."""

    def __init__(self, k: int = DEFAULT_K, seed: int = 20260801) -> None:
        self.k = k
        self.protocol = ArmProtocol(
            arm_id="bm25", variant="",
            segmentation_recipe_version=SEGMENTATION_RECIPE_VERSION,
            input_recipe_version="bm25-span/1", encoder_id=None, schema_version=None,
            k=k, max_spans_read=k, max_whole_file_reads=0,
            read_budget_bytes=READ_BUDGET_BYTES, rounds=1, beam=None, max_materialized=k,
            granularity="span", fold_model_calls=0, query_model_calls=0,
            model_stamp=NO_MODEL, seed=seed,
            note=f"okapi bm25, k1={K1} b={B}, idf=ln(1+(N-df+0.5)/(df+0.5)), leaf spans",
        )
        self._postings: dict[str, list[tuple[int, int]]] = {}
        self._lengths: list[int] = []
        self._avg_len = 0.0
        self._span_ids: list[str] = []
        self._folded_universe: str | None = None

    def fold(self, view: SnapshotView, segmentation_id: str = "") -> FoldCost:
        started = time.perf_counter()
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        lengths: list[int] = []
        span_ids: list[str] = []
        total_bytes = 0

        for index, span in enumerate(view.leaf_spans):
            text = view.span_text(span)
            total_bytes += len(text.encode("utf-8"))
            counts: dict[str, int] = defaultdict(int)
            for token in tokenize(text):
                counts[token] += 1
            for token, tf in counts.items():
                postings[token].append((index, tf))
            lengths.append(sum(counts.values()))
            span_ids.append(span.span_id)

        self._postings = dict(postings)
        self._lengths = lengths
        self._avg_len = (sum(lengths) / len(lengths)) if lengths else 0.0
        self._span_ids = span_ids
        self._folded_universe = view.universe_id
        wall = time.perf_counter() - started
        # BM25 keeps no cache on disk: every fold is a build, so the bill and this call agree.
        return FoldCost(
            wall_seconds=wall, wall_seconds_this_call=wall, model_calls=0, model_tokens=0,
            vectors_built=0, bytes_stored=total_bytes, cached=False,
        )

    def _rank(self, view: SnapshotView, question: str) -> list[tuple[float, int]]:
        n_docs = len(self._lengths)
        scores: dict[int, float] = defaultdict(float)
        for token in set(tokenize(question)):
            posting = self._postings.get(token)
            if not posting:
                continue
            df = len(posting)
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            for index, tf in posting:
                denom = tf + K1 * (1 - B + B * (self._lengths[index] / (self._avg_len or 1.0)))
                scores[index] += idf * (tf * (K1 + 1)) / denom
        # Ties break on the span id - a content hash, so the order is a property of the corpus
        # and not of dictionary insertion.
        return sorted(((s, i) for i, s in scores.items()),
                      key=lambda si: (-si[0], self._span_ids[si[1]]))

    def answer(self, task: BenchTask, reader: SpanReader, models: ModelCounter) -> ArmAnswer:
        view = reader.view
        if self._folded_universe != view.universe_id:
            raise ArmUnavailable("bm25 index was folded over a different universe",
                                 folded=self._folded_universe, asked=view.universe_id)
        ranked = self._rank(view, task.question)[: self.k]
        parts: list[str] = []
        retrieved: list[str] = []
        for _score, index in ranked:
            span = view.span_by_id(self._span_ids[index])
            if span is None:
                continue
            parts.append(reader.read_span(span))
            retrieved.append(span.span_id)
        return ArmAnswer(
            context="\n".join(parts), rounds=1, retrieved=retrieved,
            note=f"top-{self.k} spans",
            detail={"scores": [round(s, 4) for s, _ in ranked],
                    "nodes": [view.span_by_id(self._span_ids[i]).node_id
                              for _, i in ranked
                              if view.span_by_id(self._span_ids[i]) is not None]},
        )
