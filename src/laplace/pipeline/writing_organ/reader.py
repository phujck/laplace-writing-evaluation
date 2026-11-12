"""The bounded prefix reader: the low-bandwidth linear reader as machinery.

Streams a manuscript in order. Carries ONLY a bounded ReaderState between chunks -
low bandwidth is architecturally enforced, not roleplayed. Per chunk it emits typed
findings and per-sentence function labels; a sentence earning no function is EMPTY.
Comprehension-per-token is bookkept from the labels: what the chunk cost against
what it discharged.

The reading itself is dispatched (a capacity-limited model, stamped explicitly per
the dispatch kernel). This module compiles the prompts, parses returns, carries the
ledger, and scores. It never edits prose.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from laplace.pipeline.writing_organ.schema import Finding, ReaderState, prepare_read

PARA_ANCHOR = re.compile(r"^%\s*(sec:[\w:-]+-p\d+)\s*$", re.MULTILINE)


def chunk_tex(tex: str, section: str, paras_per_chunk: int = 4) -> list[tuple[str, str]]:
    """Split a section tex file on paragraph anchors into (anchor-range, text) chunks."""
    pieces = PARA_ANCHOR.split(tex)
    paras: list[tuple[str, str]] = []
    for i in range(1, len(pieces) - 1, 2):
        paras.append((pieces[i], pieces[i + 1].strip()))
    if not paras:
        paras = [(f"{section}-whole", tex.strip())]
    chunks = []
    for i in range(0, len(paras), paras_per_chunk):
        group = paras[i:i + paras_per_chunk]
        label = f"{group[0][0]}..{group[-1][0]}" if len(group) > 1 else group[0][0]
        chunks.append((label, "\n\n".join(f"% {a}\n{t}" for a, t in group)))
    return chunks


READER_RETURN_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "anchor": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["kind", "anchor", "text"],
            },
        },
        "sentence_functions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sentence": {"type": "string"},
                    "function": {"type": "string"},
                },
                "required": ["sentence", "function"],
            },
        },
        "newly_defined": {"type": "object", "additionalProperties": {"type": "string"}},
        "newly_established": {"type": "object", "additionalProperties": {"type": "string"}},
        "new_open_questions": {"type": "array", "items": {"type": "string"}},
        "closed_questions": {"type": "array", "items": {"type": "string"}},
        "updated_summary": {"type": "string"},
        "next_need": {"type": "string"},
    },
    "required": ["findings", "sentence_functions", "updated_summary"],
}


class ReaderContextInsufficient(ValueError):
    """This attempted next read needs more named premises than the bounded reader holds. Only this read is
    refused; ``details`` carries the missing names, one local obligation and the finite focused continuation."""

    def __init__(self, admission: dict):
        super().__init__(admission["obligation"]["reason"])
        self.details = admission


def compile_reader_prompt(state: ReaderState, chunk_label: str, chunk_text: str, *,
                          audience: str = "physics manuscript") -> str:
    """One progressive read: the state and THIS stretch only (never later text). ``audience`` registers
    the reader for the document's actual readers (e.g. a business plan) instead of one domain prior.
    A state whose next read needs premises it could not hold is refused (ReaderContextInsufficient):
    no prompt presents an insufficient context as a normal one; ReadRun.prompt(focus=...) continues."""
    prepared, admission = prepare_read(state)   # the one rule: normalize, then admit, then render that state
    if not admission["sufficient"]:
        raise ReaderContextInsufficient(admission)
    return f"""You are a low-bandwidth linear reader of a {audience}. You read strictly
in order; the text below is the next stretch, and the READER STATE is everything you
remember of what came before. You have never seen any other draft of this paper and
know nothing about its revision history.

{prepared._render_prepared()}

NEXT STRETCH ({chunk_label}):
---
{chunk_text}
---

Report, honestly and only from what you hold:
1. findings - typed defects, kinds: undefined-symbol (used before you hold it),
   forward-reference (depends on something you don't have yet), lost-state (assumes
   you remember something not in your state), repetition (you already hold this;
   nothing new), empty-sentence (says nothing / fills space / circular), process-leak
   (references drafts, earlier versions, or the authors' workflow), type-upgrade
   (asserts as exact what your state holds as conditional or empirical), economy
   (detail that costs you context without helping you understand), register
   (telegraphic fragments, uniform mic-drop emphasis, or commentary-to-the-author
   tone rather than prose for a reader). Anchor each to the
   paragraph anchor. Only report real defects; an empty list is a valid answer.
   (The register kind exists because the Gate-1 bench measured its absence: the
   2026-08-08 run missed the two cadence/register calibration rows for want of a
   type to report them with.)
2. sentence_functions - EVERY sentence in the stretch, labelled with exactly one of:
   define, claim, support, discharge, orient, EMPTY. Be strict: a sentence that
   restates what you hold, or asserts importance without content, is EMPTY.
3. newly_defined / newly_established - symbols and claims this stretch actually gave
   you (one line each). Do not credit what it merely mentioned.
4. new_open_questions / closed_questions - what it opened for you, what it closed.
5. updated_summary - your running summary rewritten, at most 300 words. Anything you
   cannot fit, you lose; that is the point. Spend it on concrete content, not on repeating
   that something is uncertain: attach any uncertainty to the one claim it qualifies.
6. next_need - one line: what you need the next stretch to give you, naming the exact
   symbols, claims or requirements it depends on (those are kept for you when you name them).

Return the JSON only."""


@dataclass
class ChunkScore:
    label: str
    tokens: int
    discharged: int      # define + claim + support + discharge labels
    empty: int
    findings: int

    @property
    def comprehension_per_kilotoken(self) -> float:
        return 1000.0 * self.discharged / max(self.tokens, 1)


@dataclass
class ReadRun:
    """Accumulates a full linear read: state evolution, findings, economy scores."""

    state: ReaderState = field(default_factory=ReaderState)
    findings: list[Finding] = field(default_factory=list)
    scores: list[ChunkScore] = field(default_factory=list)
    # What left the bounded state (never rendered as memory): the useful prefix a focused continuation restores.
    history: dict = field(default_factory=lambda: {"defined": {}, "established": {}})
    obligations: list = field(default_factory=list)   # typed local obligations, each once (laplace.core.scoped)
    _seq: int = 0

    def _bound(self) -> None:
        """Normalize the run state by the one rule, archiving every evicted meaning into history first."""
        from laplace.core import scoped as core_scoped
        self.state, admission = prepare_read(self.state, self.history)
        if not admission["sufficient"]:
            self.obligations = core_scoped.merge(self.obligations, [admission["obligation"]])

    def prompt(self, chunk_label: str, chunk_text: str, *, audience: str = "physics manuscript", focus=None) -> str:
        """The next read's prompt. Without ``focus`` it is the normal progressive read and refuses when the needed
        context does not fit. With ``focus`` (one batch of the refused read's continuation) it is a focused read:
        those named premises, restored from this run's history, within the bound; the run state is not changed."""
        self._bound()   # whatever entered the run state (constructor, absorb) is archived before it can be lost
        if focus is None:
            return compile_reader_prompt(self.state, chunk_label, chunk_text, audience=audience)
        admission = self.state.admission()
        batches = (admission.get("continuation") or {}).get("batches") or []
        if list(focus) not in batches:
            raise ValueError("A focused read names exactly one batch of the refused read's continuation.")
        focused = ReaderState(defined=dict(self.state.defined), established=dict(self.state.established),
                              open_questions=list(self.state.open_questions), summary=self.state.summary,
                              next_need=self.state.next_need, focus=list(focus))
        for kind in ("defined", "established"):
            getattr(focused, kind).update({name: meaning for name, meaning in self.history[kind].items() if name in focus})
        # Admitted only if every focused premise is actually held after restoration; absent history refuses locally.
        return compile_reader_prompt(focused, chunk_label + " (focused " + str(batches.index(list(focus)) + 1)
                                     + " of " + str(len(batches)) + ")", chunk_text, audience=audience)

    def absorb(self, chunk_label: str, chunk_text: str, result: dict, source: str) -> None:
        for f in result.get("findings", []):
            self._seq += 1
            self.findings.append(Finding(
                id=f"WR-{self._seq:03d}", kind=f.get("kind", "unknown"),
                anchor=f.get("anchor", chunk_label), text=f.get("text", ""), source=source))
        labels = [s.get("function") for s in result.get("sentence_functions", [])]
        useful = sum(1 for l in labels if l in ("define", "claim", "support", "discharge"))
        empty = sum(1 for l in labels if l == "EMPTY")
        self.scores.append(ChunkScore(
            label=chunk_label, tokens=len(chunk_text.split()),
            discharged=useful, empty=empty, findings=len(result.get("findings", []))))
        self.state.defined.update(result.get("newly_defined", {}))
        self.state.established.update(result.get("newly_established", {}))
        closed = set(result.get("closed_questions", []))
        self.state.open_questions = [q for q in self.state.open_questions if q not in closed]
        self.state.open_questions.extend(result.get("new_open_questions", []))
        self.state.summary = result.get("updated_summary", self.state.summary)
        self.state.next_need = result.get("next_need", self.state.next_need)
        self._bound()

    def report(self) -> str:
        lines = ["anchor-range                                tok  useful empty findings  compr/ktok"]
        for s in self.scores:
            lines.append(f"{s.label:<42} {s.tokens:>4} {s.discharged:>6} {s.empty:>5} "
                         f"{s.findings:>8} {s.comprehension_per_kilotoken:>10.1f}")
        total_tok = sum(s.tokens for s in self.scores)
        total_empty = sum(s.empty for s in self.scores)
        lines.append(f"TOTAL tokens={total_tok} empty-sentences={total_empty} findings={len(self.findings)}")
        return "\n".join(lines)

    def dump_findings(self) -> str:
        return "\n".join(f.to_row() for f in self.findings)
