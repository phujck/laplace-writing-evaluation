"""grep_skilled.py - v1 arm C, ported: a pattern derived from the QUESTION STRING ONLY.

This is the honest mechanical baseline, and its honesty rests on one property: the pattern is
derived from the question and from nothing else. ``assert_no_leak`` is the mechanism - a pattern
word that occurs in a must-atom but NOT in the question was derived from the answer, and the run
refuses rather than reporting a rigged win. It fires on every task, every round.

The derivation, ported unchanged from v1 ``derive_pattern``: take the question's kept tokens
(length >= 4, minus a stopword list), form adjacent bigrams, rank them by how many corpus files
match, and take the RAREST bigram that hits anywhere. If no bigram hits, take the rarest hitting
single token; if nothing hits, OR the first six tokens. That models the skilled move - choose the
rarest distinctive phrase - and it is deterministic and re-derivable from the question text.

Two rounds, exactly as v1: round 1 is the grep view alone (a skilled agent checks whether the
matches already answer before opening anything); round 2 opens the top hit files, at most three,
whole if small and as +-40-line hit regions if over 64 KB.

WHAT IS NOT CHARGED, ported with its caveat. The frequency-counting greps that model a human
choosing a distinctive keyword were not charged in v1 - the arm is measured at its best case, and
the caveat said so. Here the bytes they scan are recorded as ``scan_bytes``: reported beside the
bill, never inside it, so the best-case framing is visible instead of implicit.

TWO PORTED BEHAVIOURS CHANGED, both forced by the snapshot and both stated. (1) v1 shelled out to
``grep -r`` and inherited the filesystem's walk order; here the corpus is walked in sorted node
order, which is deterministic across machines. (2) v1's ``--include`` globs selected .md, .py and
.jsonl from the working tree; here the same three extensions select from the view, so the
excluded universe is respected without the arm knowing about it.
"""

from __future__ import annotations

import re

from ...segment import SEGMENTATION_RECIPE_VERSION
from ..cost import ModelCounter, SpanReader
from ..protocol import NO_MODEL, ArmProtocol
from ..scoring import assert_no_leak, score
from ..task import BenchTask
from ..universe import SnapshotView
from .base import ArmAnswer, BaseArm

# --- v1 constants, ported verbatim -----------------------------------------
GREP_INCLUDES = (".md", ".py", ".jsonl")
GREP_MAX_LINES = 100
GREP_CONTEXT = 3
GREP_LINE_CAP = 400          # the `| cut -c1-400` a skilled agent pipes jsonl-heavy grep through
MAX_WHOLE_READS = 3
WHOLE_READ_CAP = 64 * 1024   # above this, hit regions instead of the whole file
REGION_LINES = 40
REGION_LINE_CAP = 2000
MAX_REGION_HITS = 50         # a reader stops scanning a huge file at some point

STOPWORDS = set(
    """a an and are at be been by did do does for from had has have how in is it its may
    must name of on or once that the this to under was were what which who with when
    where why not no still and-what state current currently"""
    .split()
)

READ_BUDGET_BYTES = 8 * 1024 * 1024


def question_tokens(question: str) -> list[str]:
    """Kept tokens of the question, in order, deduplicated. Ported."""
    words = re.findall(r"[a-z0-9][a-z0-9_./-]{3,}", question.casefold())
    kept = [w for w in words if w not in STOPWORDS]
    seen: set[str] = set()
    out: list[str] = []
    for w in kept:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _grep_nodes(view: SnapshotView) -> list[str]:
    return [n for n in view.node_ids if n.endswith(GREP_INCLUDES)]


class GrepSkilledArm(BaseArm):
    """Pattern from the question, two bounded rounds, line caps, leakage assertion on every task."""

    def __init__(self, seed: int = 20260801) -> None:
        self.protocol = ArmProtocol(
            arm_id="grep_skilled", variant="",
            segmentation_recipe_version=SEGMENTATION_RECIPE_VERSION,
            input_recipe_version="grep-skilled/1", encoder_id=None, schema_version=None,
            k=MAX_WHOLE_READS, max_spans_read=0, max_whole_file_reads=MAX_WHOLE_READS,
            read_budget_bytes=READ_BUDGET_BYTES, rounds=2, beam=None, max_materialized=None,
            granularity="node", fold_model_calls=0, query_model_calls=0,
            model_stamp=NO_MODEL, seed=seed,
            note=("v1 arm C ported: pattern derived from the question string only, leakage "
                  "asserted; frequency probes are reported as scan_bytes and not charged"),
        )
        self._nodes: list[str] = []

    # --- the derivation ---------------------------------------------------

    def file_frequency(self, view: SnapshotView, pattern: str, reader: SpanReader) -> int:
        """How many corpus files match the pattern. The skill probe: scanned, not charged."""
        rx = re.compile(pattern, re.IGNORECASE)
        hits = 0
        for node_id in self._nodes:
            text = view.node_text(node_id)
            reader.scan(len(text.encode("utf-8")))
            if rx.search(text):
                hits += 1
        return hits

    def derive_pattern(self, view: SnapshotView, question: str, reader: SpanReader) -> str:
        """Pattern from the QUESTION string only - deterministic, re-derivable. Ported."""
        toks = question_tokens(question)
        bigrams = [rf"{re.escape(a)}[\s-]+{re.escape(b)}" for a, b in zip(toks, toks[1:], strict=False)]
        ranked_bi = sorted((self.file_frequency(view, b, reader), b) for b in bigrams)
        useful_bi = [b for n, b in ranked_bi if n > 0]
        if useful_bi:
            return useful_bi[0]
        ranked = sorted((self.file_frequency(view, re.escape(t), reader), t) for t in toks)
        useful = [t for n, t in ranked if n > 0]
        if not useful:
            return "|".join(re.escape(t) for t in toks[:6])
        return re.escape(useful[0])

    # --- the two rounds ---------------------------------------------------

    def run_grep(self, view: SnapshotView, pattern: str, reader: SpanReader) -> str:
        """grep -rniE -C3 over the view, in sorted node order, with v1's line caps."""
        rx = re.compile(pattern, re.IGNORECASE)
        out: list[str] = []
        budget = GREP_MAX_LINES * (2 * GREP_CONTEXT + 1)
        for node_id in self._nodes:
            text = view.node_text(node_id)
            reader.scan(len(text.encode("utf-8")))
            # Whole-text probe before splitting: a node with no match anywhere emits no lines, so
            # skipping its line walk cannot change the output - only the seconds it costs.
            if not rx.search(text):
                continue
            lines = text.splitlines()
            emitted: set[int] = set()
            for i, line in enumerate(lines):
                if not rx.search(line):
                    continue
                lo = max(0, i - GREP_CONTEXT)
                hi = min(len(lines), i + GREP_CONTEXT + 1)
                for j in range(lo, hi):
                    if j in emitted:
                        continue
                    emitted.add(j)
                    sep = ":" if rx.search(lines[j]) else "-"
                    out.append(f"./{node_id}{sep}{j + 1}{sep}{lines[j]}"[:GREP_LINE_CAP])
                    if len(out) >= budget:
                        return "\n".join(out)
        return "\n".join(out)

    @staticmethod
    def hit_files(grep_out: str) -> list[str]:
        """Files ranked by match count, exactly as v1 read its own grep output."""
        counts: dict[str, int] = {}
        for line in grep_out.splitlines():
            m = re.match(r"^\./([^:]+):\d+:", line)
            if m:
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
        return [f for f, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    @staticmethod
    def charged_excerpt(text: str, pattern: str) -> str:
        """Whole file if small; otherwise the +-REGION_LINES around pattern hits. Ported."""
        if len(text.encode("utf-8")) <= WHOLE_READ_CAP:
            return text
        lines = text.splitlines()
        rx = re.compile(pattern, re.IGNORECASE)
        keep: set[int] = set()
        hits = 0
        for i, ln in enumerate(lines):
            if rx.search(ln):
                hits += 1
                if hits > MAX_REGION_HITS:
                    break
                keep.update(range(max(0, i - REGION_LINES),
                                  min(len(lines), i + REGION_LINES + 1)))
        if not keep:
            return "\n".join(ln[:REGION_LINE_CAP] for ln in lines[: 2 * REGION_LINES])
        return "\n".join(lines[i][:REGION_LINE_CAP] for i in sorted(keep))

    def answer(self, task: BenchTask, reader: SpanReader, models: ModelCounter) -> ArmAnswer:
        view = reader.view
        self._nodes = _grep_nodes(view)
        pattern = self.derive_pattern(view, task.question, reader)
        assert_no_leak(pattern, task.atoms, task.task_id, task.question)

        context = reader.read_text(self.run_grep(view, pattern, reader))
        files = self.hit_files(context)
        rounds = 1
        opened: list[str] = []

        if not score(context, task.atoms, task.window)[0]:
            rounds = 2
            pat = pattern
            if not files:
                toks = question_tokens(task.question)
                pat = "|".join(re.escape(t) for t in toks[:6])
                assert_no_leak(pat, task.atoms, task.task_id, task.question)
                context += reader.read_text(self.run_grep(view, pat, reader))
                files = self.hit_files(context)
            for node_id in files[:MAX_WHOLE_READS]:
                if not view.has_node(node_id):
                    continue
                excerpt = self.charged_excerpt(view.node_text(node_id), pat)
                context += "\n" + reader.read_node_excerpt(node_id, excerpt)
                opened.append(node_id)

        return ArmAnswer(
            context=context, rounds=rounds, retrieved=files[:MAX_WHOLE_READS],
            note=f"pattern={pattern} read={','.join(opened[:4])}",
            detail={"pattern": pattern, "opened": opened, "hit_files": files[:10]},
        )
