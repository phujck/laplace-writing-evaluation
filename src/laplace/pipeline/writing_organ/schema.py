"""Typed objects the writing organ operates on."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict

EPISTEMIC_TYPES = (
    "theorem",            # rigorous, assumption-free within the stated model
    "exact-under-assumptions",  # exact given stated grid/alignment/symmetry assumptions
    "empirical",          # measured regularity, no derivation
    "conjecture",         # stated direction, no protocol
)

SENTENCE_FUNCTIONS = (
    "define",     # introduces a symbol or object
    "claim",      # states a claim (must carry a claim id)
    "support",    # supports a prior claim (derivation step, evidence, citation)
    "discharge",  # closes an open reader question
    "orient",     # tells the reader where the argument is going (budgeted, rare)
    "EMPTY",      # earns no label: says nothing new, restates, or is circular
)


@dataclass
class Claim:
    id: str
    text: str
    epistemic_type: str            # one of EPISTEMIC_TYPES
    supports: list[str] = field(default_factory=list)   # claim ids / computation ids / cite keys
    section: str = ""
    anchor: str = ""               # paragraph anchor, e.g. sec:r2_theory_laws-p1
    check: str = ""                # auditor check id when computation-linked

    def to_row(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class Finding:
    id: str
    kind: str        # e.g. empty-sentence, ungrounded-claim, forward-reference, lost-state,
                     # repetition, weld, wrong-derivation, type-upgrade, process-leak, economy
    anchor: str
    text: str
    severity: str = "defect"   # defect | style | question
    source: str = ""           # which instrument produced it
    status: str = "open"       # open | fixed | ruled-out

    def to_row(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


BEATS = ("question", "intuition", "prediction", "derivation", "test", "consequence")
#: The edge-realisation order of the cut law (DESIGN_2026-08-08b section 3): each
#: movement opens on its bridge, makes the equation formalise what the reader already
#: understands, predicts before deriving, tests with figures as illustration, and
#: hands off. The contract carries it so writers commit inside it.


@dataclass
class MovementContract:
    id: str
    establishes: list[str]         # claim ids this movement must establish, in order
    assumes: list[str]             # claim ids available from the prefix (all it may rely on)
    word_budget: int
    question: str = ""             # the sub-question this movement answers (the telling's)
    beats: tuple = BEATS           # the edge-realisation order (cut law section 3)
    breath_budget: int = 1         # orientation sentences licensed at the opening seam
                                   # (cut size / 12, min 1 - breath.py computes it)
    frozen: list[str] = field(default_factory=list)  # verbatim passages that must survive
    forbidden: list[str] = field(default_factory=list)  # e.g. references to drafts/process


@dataclass
class ReaderState:
    """What the bounded reader holds. The ledger IS its memory: anything not here is lost.

    Four kinds of knowledge, each bounded: what it already holds (``defined``/``established``:
    prior knowledge and newly acquired understanding), what it is asking (``open_questions``) and
    what it needs next (``next_need``). Scoped progress (laplace.core.scoped) applies to the bound:
    the held names that an open question or the next need refers to are the premises that next read
    consumes, so they are retained first; unreferenced entries go oldest-first. Repeated sentences in
    the summary (a generic non-claim said again) are dropped before any premise is.
    """

    defined: dict[str, str] = field(default_factory=dict)   # symbol -> one-line meaning
    established: dict[str, str] = field(default_factory=dict)  # claim id -> one-line content
    open_questions: list[str] = field(default_factory=list)
    summary: str = ""              # running prose summary, hard-capped
    next_need: str = ""            # what this reader needs from the next stretch or action
    insufficient: list[str] = field(default_factory=list)  # needed premises the bound could not hold
    focus: list[str] = field(default_factory=list)  # a focused continuation read needs only these names

    SUMMARY_CAP_WORDS = 350
    MAX_OPEN_QUESTIONS = 12
    MAX_QUESTION_WORDS = 60
    MAX_HELD = 40                  # defined + established entries together
    NEXT_NEED_CAP_WORDS = 60

    def _need_text(self) -> str:
        return " ".join(self.open_questions + [self.next_need])

    @staticmethod
    def _named(name, text) -> bool:
        return re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", text) is not None

    def consumed_names(self) -> list[str]:
        """Held names the open questions or the next need refer to: the premises the next read consumes
        (only the focused ones in a focused continuation read)."""
        text = self._need_text()
        names = [name for name in list(self.defined) + list(self.established) if self._named(name, text)]
        return [name for name in names if name in self.focus] if self.focus else names

    def missing_premises(self, names) -> list[str]:
        """Named premises a next read refers to that this state does not hold."""
        return [name for name in names if name not in self.defined and name not in self.established]

    def enforce_bounds(self) -> dict:
        """Bound every field. Returns what left the held ledgers ({'defined', 'established'}) so a caller keeps it
        as history; nothing needed is dropped silently: a needed premise the bound cannot hold is named in
        ``insufficient`` and makes the next read inadmissible (``admission``) until it is read in focused parts."""
        sentences, seen = [], set()
        for sentence in re.split(r"(?<=[.!?])\s+", self.summary.strip()):
            key = " ".join(sentence.lower().split())
            if key and key not in seen:
                seen.add(key)
                sentences.append(sentence)
        words = " ".join(sentences).split()
        if len(words) > self.SUMMARY_CAP_WORDS:
            words = words[-self.SUMMARY_CAP_WORDS:]
        self.summary = " ".join(words)
        self.open_questions = [" ".join(q.split()[:self.MAX_QUESTION_WORDS]) for q in self.open_questions[-self.MAX_OPEN_QUESTIONS:]]
        self.next_need = " ".join(self.next_need.split()[:self.NEXT_NEED_CAP_WORDS])
        text = self._need_text()
        insufficient = [name for name in self.insufficient if self._named(name, text)
                        and (not self.focus or name in self.focus) and self.missing_premises([name])]
        evicted = {"defined": {}, "established": {}}
        held = len(self.defined) + len(self.established)
        if held > self.MAX_HELD:
            keep = self.consumed_names()
            excess = held - self.MAX_HELD
            for kind, ledger in (("defined", self.defined), ("established", self.established)):
                for name in [n for n in ledger if n not in keep]:   # oldest unreferenced first; symbols before claims
                    if excess <= 0:
                        break
                    evicted[kind][name] = ledger.pop(name)
                    excess -= 1
            for name in keep[self.MAX_HELD:] if excess > 0 else []:   # the needed premises themselves overflow
                kind = "defined" if name in self.defined else "established"
                evicted[kind][name] = getattr(self, kind).pop(name)
                insufficient.append(name)
        self.insufficient = list(dict.fromkeys(insufficient))
        return evicted

    def admission(self) -> dict:
        """Whether this state's next read is admitted, by the one rule (``prepare_read``) on a normalized copy:
        never from un-normalized fields. Insufficient: the missing names, one typed local obligation and a finite
        continuation."""
        return prepare_read(self)[1]

    def _normalized_admission(self) -> dict:
        """Admission of an already normalized state (called only by prepare_read)."""
        if self.focus:
            absent = self.missing_premises(self.focus)
            if absent:
                return _focus_unavailable(self, absent)
        if not self.insufficient:
            return {"sufficient": True}
        from laplace.core import identity as core_identity, scoped as core_scoped
        needed = list(dict.fromkeys(self.consumed_names() + self.insufficient))
        batches = [needed[index:index + self.MAX_HELD] for index in range(0, len(needed), self.MAX_HELD)]
        return {"sufficient": False, "missing": list(self.insufficient), "needed": len(needed),
                "obligation": core_scoped.obligation(
                    "READER_CONTEXT_INSUFFICIENT",
                    "The next read needs %d named premises; this reader holds at most %d. Read it in %d focused parts."
                    % (len(needed), self.MAX_HELD, len(batches)),
                    subject="next-read", basis=core_identity.canonical_digest(sorted(needed)), key="needed-context-overflow"),
                "continuation": {"kind": "focused-reads", "batches": batches}}

    def render(self) -> str:
        """The rendered memory of this state as the one rule prepares it (a normalized copy; this state is not
        changed). A prompt renders the exact state its admission was decided on."""
        return prepare_read(self)[0]._render_prepared()

    def _render_prepared(self) -> str:
        lines = ["READER STATE (this is ALL you remember; anything not listed here you have lost)"]
        if self.defined:
            lines.append("Symbols you hold: " + "; ".join(f"{k}: {v}" for k, v in self.defined.items()))
        if self.established:
            lines.append("Claims you hold: " + "; ".join(f"[{k}] {v}" for k, v in self.established.items()))
        if self.open_questions:
            lines.append("Questions still open for you: " + " | ".join(self.open_questions))
        if self.summary:
            lines.append("Your running summary: " + self.summary)
        if self.next_need:
            lines.append("What you need next: " + self.next_need)
        if self.focus:
            lines.append("This read covers only: " + ", ".join(self.focus))
        if self.insufficient:
            lines.append("Premises you need but could NOT hold (lost under your memory bound): " + ", ".join(self.insufficient))
        return "\n".join(lines)


def _focus_unavailable(state, absent) -> dict:
    """A focused read whose named premises are not actually held: refused locally, with its finite recovery."""
    from laplace.core import identity as core_identity, scoped as core_scoped
    return {"sufficient": False, "missing": list(absent), "needed": len(state.focus),
            "obligation": core_scoped.obligation(
                "READER_CONTEXT_INSUFFICIENT",
                "This focused read needs %d named premises that this reader does not hold and cannot restore: %s. "
                "Restore them from the run history that evicted them, or reread the stretch that introduced them."
                % (len(absent), ", ".join(absent[:12]) + (" ..." if len(absent) > 12 else "")),
                subject="focused-read", basis=core_identity.canonical_digest(sorted(state.focus)), key="focused-premises-unavailable"),
            "continuation": {"kind": "restore-premises", "missing": list(absent)}}


def prepare_read(state, history=None):
    """THE one prompt-preparation rule for every reader entry (direct compile, render, run prompt, focused prompt).

    1. normalize a copy: bound every field; meanings that leave the held ledgers are added to ``history``
       (when given) before anything can discard them, and needed premises the bound cannot hold become
       ``insufficient``;
    2. admit that prepared state: sufficient only if nothing needed is insufficient and, for a focused read,
       every focused premise is actually held (restored meaning, not an asserted name);
    3. the caller renders exactly that prepared state (``_render_prepared``); nothing changes after admission.
    Returns (prepared_state, admission). The input state is never mutated."""
    import copy
    prepared = copy.deepcopy(state)
    evicted = prepared.enforce_bounds()
    if history is not None:
        for kind, rows in evicted.items():
            history.setdefault(kind, {}).update(rows)
    return prepared, prepared._normalized_admission()
