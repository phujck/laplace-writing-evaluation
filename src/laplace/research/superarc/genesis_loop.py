"""genesis_loop.py — B13: the item-genesis loop, per-item and then global.

The loop is synthetics-genesis's shape transposed onto one benchmark item, with
the two organs that did not carry rebuilt rather than ported (DESIGN_2026-08-04
§4). Read the corrections first, because each one is a defect measured in the
original:

* **P0 is the sequence, verbatim, never edited.** :py:func:`prompt_zero` returns
  the item's literal and nothing else, and every later P_n is a FULL rewrite
  composed from that literal plus the typed residue account — never an edit of
  P_{n-1}. :py:func:`carries_p0` is the mechanical statement of the discipline.
* **The rewrite cadence is residue-driven, not per-round.** A round that produces
  no residue the account does not already carry produces no rewrite, and the
  absence is banked as its own row — in the original that silence was itself a
  convergence signal, and a silent no-op would have erased it.
* **Convergence is φ-relevant progress, and it is a NEW organ.**
  ``detect_recursion.py`` fires on the PRESENCE of a worked recursion and is the
  opposite polarity; the organ that encoded "stopped shrinking" was hand-authored
  with no producing script. Here the trigger is a verified-correct model found,
  or an existing verified model promoted to a better bin — φ is a step function
  at correctness, so residue shrinkage on an item that never closes is worth
  exactly zero. It is computed from append-only round-stamped rows ALONE
  (:py:func:`convergence`), raises on a non-integer round key instead of
  degrading to a silent ``false``, and deduplicates by candidate id before any
  count. The original read a mutable single-state file and could not reproduce
  its own history.
* **δ is measured, never optimized.** Nothing in this module's selection path
  touches nBDM or δ: :py:func:`select_best` ranks by BIN alone, because bin
  promotion is a 10–100× φ move that swamps any δ movement, while δ is a
  length-normalized density that a shorter program RAISES. The metric is not
  named in any composed packet either — the instrument that scores us is never
  what the worker optimizes against.
* **Submission is a GLOBAL post-run decision.** A bin's contribution is
  quadratic in bin size and harmonic in δ, so a per-item gate cannot express what
  adding one answer does to φ. The preregistered rule is
  :data:`SUBMISSION_RULE` — every item, always, best available bin, no selection
  — and :py:func:`compare_submission_sets` exists to DISCLOSE the interaction
  (evaluated through :py:func:`laplace.research.superarc.phi.from_ledger`), not to choose.
* **The motive law (his ruling, 2026-08-04).** Composed packets are
  success-framed: the generator exists and is findable, and no packet offers the
  worker an option of failure (:py:func:`motive_violations`, enforced at
  composition). Truthfulness is not the worker's job — the bench records divergence,
  the ledger types it, this module judges convergence. Motive up front, truth at
  the gate; they live in different organs and so never trade.

The model call is a SEAM, not a dependency: :py:data:`Proposer` is any callable
from a :py:class:`Packet` to candidate :py:class:`Proposal` s. Tests run a stub
proposer, a live run plugs a dispatcher. ``scripts/packet.py`` is a pattern here,
not an import — it hardcodes its project, worker, effort and its own depth — so
the composition rides ``dispatch.kernel`` + ``schema.fence`` + ``schema.clamp_model``
directly and carries an EXPLICIT model stamp, never inheritance.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from laplace.pipeline import dispatch, registry, schema

from . import phi, submission_gate
from . import sequence_exec as sx
from .bin_classifier import Bin, classify

#: Frozen tag. The ledger banks verdicts under it; a changed decision rule needs
#: a new tag or the banked rows stop meaning what they said.
LOOP_VERSION: str = "b13-1"

OBSERVED_BY: str = f"superarc genesis_loop {LOOP_VERSION}"

PROJECT: str = "superarc"
WORKER: str = "derive"
EFFORT: str = "medium"

REPO = source_tree()
CAMPAIGN_DIR = REPO / "synthetics papers" / "superarc"
GENESIS_PATH = CAMPAIGN_DIR / "genesis" / "genesis.jsonl"
CAPABILITY_GAPS_PATH = CAMPAIGN_DIR / "genesis" / "capability_gaps.jsonl"

# --------------------------------------------------------------------------- #
# Bounds and closed sets — named, never inline
# --------------------------------------------------------------------------- #

#: The lenses, fixed before any arm runs. Distinct enough that two of them
#: failing is two observations rather than one repeated.
LENSES: tuple[str, ...] = (
    "difference-table",
    "closed-form",
    "automaton",
    "number-theoretic",
    "self-referential",
)

LENS_FRAMES: dict[str, str] = {
    "difference-table": (
        "Build the difference table (and the difference of differences) and read the "
        "recurrence off it. A finite difference column that goes constant IS the model."
    ),
    "closed-form": (
        "Find the closed form a(n) — an expression in n alone, evaluated per position, "
        "carrying none of the item's own terms."
    ),
    "automaton": (
        "Read the item as the output tape of a small machine: a bit-rule over a sliding "
        "window, a state machine, a cellular rule. Recover the rule and the seed."
    ),
    "number-theoretic": (
        "Read the positions arithmetically: divisibility, residues, primality, digit "
        "functions. The generator is a predicate on n."
    ),
    "self-referential": (
        "Read the item as generated from its own prefix: a substitution/morphism, a "
        "run-length reading of itself, a fold of an earlier segment."
    ),
}

#: How many lenses a round dispatches by default: all of them. k is a knob so a
#: budget-pressed round can narrow, never so the set can quietly change.
DEFAULT_K: int = len(LENSES)

#: The per-item round ceiling.
MAX_ROUNDS_PER_ITEM: int = 6

#: Preregistered abandonment threshold on P(closure within the rounds left).
#: Below it the item is abandoned and its remaining rounds are reallocated to
#: unattempted items: shrinking residue on an item that never closes converts
#: budget into zero φ while an easy generator sits unattempted.
ABANDON_P_THRESHOLD: float = 0.25

#: The ledger's row kinds. Observation rows carry the spine plus their own
#: fields; ``transition`` rows additionally carry the six items.
ROW_KINDS: tuple[str, ...] = (
    "candidate",     # one proposal executed and byte-compared
    "residue",       # a typed divergence from the bench
    "verified",      # a candidate whose output was byte-identical to the item
    "promotion",     # a verified model re-banked in a better bin
    "withdrawal",    # supersedes an earlier row; never an overwrite
    "transition",    # P_n -> P_{n+1}, the six items
    "no-rewrite",    # the round produced no new residue: P_n stands
    "abandonment",   # the allocation rule dropped the item
    "gap",           # routed to capability-gaps
    "submission",    # the item's scored answer, as φ reads it
)

#: The one spine every row carries.
SPINE: tuple[str, ...] = ("row_id", "item_id", "round", "kind", "subject", "observed_by")

#: The six items a transition row carries when the account is rewritten.
SIX_ITEMS: tuple[str, ...] = (
    "prior_representation",
    "evidence_explained",
    "residue_unabsorbed",
    "change_introduced",
    "new_closure",
    "new_residue",
)

#: A withdrawal keeps the practiced uppercase verb tag AND gains the machine
#: ``supersedes`` the original lacked.
WITHDRAWAL_TAGS: tuple[str, ...] = (
    "WITHDRAWN", "SUPERSEDED", "CORRECTION", "DOWNGRADE", "REVERSAL", "MEANING SHIFT",
)

#: What a withdrawal takes back. The distinction is load-bearing and typed
#: because the two are not the same claim: a promotion retires the OLD ANSWER as
#: the item's submission of record while the verification it rests on stands and
#: stays in the convergence record; only a ``verification`` withdrawal says the
#: byte-compare itself no longer holds, and only that one can un-converge an
#: item.
WITHDRAWAL_SCOPES: tuple[str, ...] = ("verification", "submission-of-record")

#: Typed enum for capability-gaps. ``budget-exhausted`` is a SEPARATE member:
#: v1 routed items we merely stopped into the same bank as items no iteration can
#: close, which inflates the paper's residual-frontier table.
WHY_ITERATION_CANNOT: tuple[str, ...] = ("missing-math", "capability", "budget-exhausted")

#: The preregistered submission rule, declared before the run.
SUBMISSION_RULE: str = "every-item-best-bin"

#: Bin order for SELECTION. Not a weighting and not a score — the ranking that
#: says a genuine abstraction beats an ordinal answer beats a print. No δ term
#: appears here or anywhere else on the selection path.
BIN_RANK: dict[Bin, int] = {
    Bin.CORRECT_NONBOTH: 3,
    Bin.CORRECT_ORDINAL: 2,
    Bin.CORRECT_PRINTS: 1,
    Bin.INCORRECT: 0,
}
TOP_BIN_RANK: int = BIN_RANK[Bin.CORRECT_NONBOTH]

#: Convergence signals — the closed set. Both are φ-relevant progress; neither is
#: residue shrinkage.
SIGNAL_FOUND: str = "verified-model-found"
SIGNAL_PROMOTED: str = "bin-promoted"
SIGNALS: tuple[str, ...] = (SIGNAL_FOUND, SIGNAL_PROMOTED)

#: Residue rows carried into a rewritten prompt, at most. The bench's own cap.
MAX_ACCOUNT_ROWS: int = sx.MAX_RESIDUE_ROWS


# --------------------------------------------------------------------------- #
# The motive law
# --------------------------------------------------------------------------- #

MOTIVE: str = (
    "The generator exists and it is findable. This item was emitted by a small "
    "program and the whole of that program's output is in front of you; your piece "
    "is to recover the program. Work the lens until you have candidates, and return "
    "candidate models — never prose about the item."
)

#: The closed set of failure OFFERS. A packet containing one hands the worker the
#: option of not finding the generator, and the ruling forbids it. The engine's
#: contact law ("report what you did not finish as unfinished") is deliberately
#: not in this set: it constrains claims of completion, it does not offer failure
#: as an outcome of the work.
_FAILURE_OFFERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("if-you-cannot", re.compile(r"\bif you (?:can|could)\s*n(?:o|')t\b", re.I)),
    ("if-none-exists", re.compile(r"\bif (?:no|there is no) (?:model|generator|solution|rule)\b", re.I)),
    ("report-failure", re.compile(r"\breport (?:failure|that you (?:failed|could not))\b", re.I)),
    ("give-up", re.compile(r"\b(?:give up|stand down|abandon the item)\b", re.I)),
    ("may-be-impossible", re.compile(r"\b(?:may be|might be|is) (?:impossible|unsolvable|hopeless)\b", re.I)),
    ("no-generator", re.compile(r"\bno generator (?:exists|may exist)\b", re.I)),
    ("permission-to-fail", re.compile(r"\bit is (?:fine|ok|okay|acceptable) to (?:fail|return nothing)\b", re.I)),
    ("empty-return", re.compile(r"\breturn (?:nothing|an empty)\b", re.I)),
)

#: The scorer is never named to the worker. A packet that mentions the metric
#: invites optimization against it, which is exactly the gaming vector §4 names.
#: Word-bounded, not substring: a lens that says "morphism" is talking about
#: substitutions, not about φ.
_METRIC_MENTIONS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(rf"\b{name}\b", re.I))
    for name in ("bdm", "nbdm", "delta", "phi", "entropy", "complexity")
) + (("delta-symbol", re.compile("δ")), ("phi-symbol", re.compile("φ")))


def motive_violations(text: str) -> list[str]:
    """Names of the failure-offer clauses present in ``text``; empty is lawful."""
    return [name for name, pat in _FAILURE_OFFERS if pat.search(text)]


def metric_mentions(text: str) -> list[str]:
    """Metric names leaked into a packet. Empty is lawful."""
    return [name for name, pat in _METRIC_MENTIONS if pat.search(text)]


# --------------------------------------------------------------------------- #
# The item and the packet
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Item:
    """One benchmark item: an id and the sequence literal, comma-separated with
    no spaces (the stored convention — the separator is load-bearing)."""

    item_id: str
    sequence: str

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Item:
        return cls(item_id=str(record["item_id"]), sequence=str(record["sequence"]))

    @property
    def terms(self) -> list[str]:
        return sx.parse_sequence(self.sequence)


@dataclass(frozen=True)
class Packet:
    """One lens-framed hypothesis packet, composed and stamped.

    ``model`` is stamped explicitly and clamped on the way in — the dispatch law
    is that a packet carries its model, never inherits one."""

    item_id: str
    round: int
    lens: str
    target: str
    goal: str
    model: str
    effort: str
    prompt: str

    def as_record(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "round": self.round,
            "lens": self.lens,
            "target": self.target,
            "goal": self.goal,
            "model": self.model,
            "effort": self.effort,
            "prompt": self.prompt,
        }


@dataclass(frozen=True)
class Proposal:
    """What a proposer returns for one packet: an executable generator and the
    model it implements, written for the scored ``-formula`` column."""

    source: str
    formula: str = ""
    note: str = ""


#: The model-call seam. A stub in tests, a dispatcher in a live run.
Proposer = Callable[[Packet], Sequence[Proposal]]


def _project() -> registry.Project | None:
    """The registry row, when there is one. ``kernel`` accepts ``None`` and emits
    the generic whole, so an unregistered campaign composes rather than dies —
    a missing row must not be able to stop the loop."""
    try:
        return registry.resolve(PROJECT)
    except Exception:  # pragma: no cover - registry is data, not code
        return None


def prompt_zero(item: Item) -> str:
    """P0: the sequence, verbatim. Nothing framed around it, nothing appended —
    fragment-zero discipline is that the first representation is the object
    itself, and every later P_n is composed FROM this string, never over it."""
    return item.sequence


def carries_p0(prompt: str, item: Item) -> bool:
    """The mechanical statement of the discipline: any P_n opens with P0 byte
    for byte."""
    return prompt == item.sequence or prompt.startswith(item.sequence + "\n")


def _residue_line(row: Mapping[str, Any]) -> str:
    cls = row.get("class")
    idx = row.get("index")
    lens = row.get("lens", "?")
    rnd = row.get("round", "?")
    if idx is None:
        return f"  round {rnd} - lens {lens} - class {cls} - no positional trace"
    return (
        f"  round {rnd} - lens {lens} - class {cls} - first divergence at index {idx} "
        f"(expected {row.get('expected')!r}, got {row.get('got')!r})"
    )


def rewrite_prompt(item: Item, account: Sequence[Mapping[str, Any]],
                   verified: Mapping[str, Any] | None = None) -> str:
    """P_{n+1}: a FULL rewrite from P0 plus the typed residue account.

    The account is the bench's own record — classes from the closed set, indices
    that index the executed output — so the rewrite can only ever carry what was
    mechanically observed. When a verified model already exists the rewrite adds
    the promotion target: a semantics-preserving replacement of a table by a
    rule, which is the only parsimony this loop asks for."""
    parts = [item.sequence]
    if account:
        lines = [_residue_line(r) for r in account[:MAX_ACCOUNT_ROWS]]
        parts.append(
            "PRIOR ATTEMPTS (the bench's own record; every line is an executed "
            "candidate's byte-compare against the whole sequence):\n" + "\n".join(lines)
        )
    if verified:
        parts.append(
            "A model already reproduces the sequence exactly:\n"
            f"  {verified.get('formula') or '(program only)'}\n"
            "Promotion target: state the same model without any stored table or "
            "enumerated case list - the rule that generates those cases, evaluated "
            "at n. The replacement must reproduce the sequence byte for byte."
        )
    return "\n\n".join(parts)


def compose_packet(
    item: Item,
    prompt: str,
    lens: str,
    round_: int,
    *,
    model: str | None = None,
    effort: str = EFFORT,
    project: registry.Project | None = None,
) -> Packet:
    """Compose one lens-framed hypothesis packet through the engine kernel.

    ``scripts/packet.py`` is the pattern: kernel head, OBJECT/POLICY fences, the
    model clamp on the path. It is not imported — it pins its project, worker,
    effort and its own directory depth as module constants.

    Raises on a packet that offers failure or names the scorer: both laws are
    enforced HERE, at composition, so a violation cannot reach a worker."""
    if lens not in LENS_FRAMES:
        raise ValueError(f"unknown lens {lens!r}; the set is {LENSES}")
    if not carries_p0(prompt, item):
        raise ValueError("P_n does not open with P0 verbatim")
    target = f"item {item.item_id} - round {round_} - lens {lens}"
    goal = f"recover the generator of item {item.item_id} under the {lens} lens"
    head = dispatch.kernel(project, target, goal, WORKER)
    obj = (
        f"item: {item.item_id}\n"
        f"terms: {len(item.terms)}\n\n"
        f"P{round_} (the item's loop state; P0 is the sequence verbatim and is never "
        f"edited):\n{prompt}\n\n"
        f"lens: {lens}\n{LENS_FRAMES[lens]}"
    )
    policy = (
        "Return candidate models, never prose. Each candidate is two things:\n"
        "  * a program that, run once with no arguments, prints the WHOLE sequence "
        "in the stored convention - commas, no spaces, standard library only;\n"
        "  * the model it implements, as a formula or recurrence in n, carrying no "
        "run of the item's own terms as literal data.\n"
        "The bench executes every candidate and byte-compares its output against the "
        "whole sequence; a candidate that prints nothing does not pass. Return as "
        "many candidates as the lens supports, strongest first."
    )
    parts = [head, MOTIVE, schema.fence("OBJECT", obj), schema.fence("POLICY", policy)]
    text = "\n\n".join(parts)
    if bad := motive_violations(text):
        raise ValueError(f"packet offers failure as an option: {bad}")
    if leaked := metric_mentions(MOTIVE + obj + policy):
        raise ValueError(f"packet names the scorer: {leaked}")
    return Packet(
        item_id=item.item_id,
        round=round_,
        lens=lens,
        target=target,
        goal=goal,
        model=schema.clamp_model(model or schema.MAX_MODEL),
        effort=effort,
        prompt=text,
    )


def compose_round(
    item: Item,
    prompt: str,
    round_: int,
    *,
    lenses: Sequence[str] = LENSES,
    k: int = DEFAULT_K,
    model: str | None = None,
    project: registry.Project | None = None,
) -> list[Packet]:
    """The round's k packets, one per lens. Composed, never sent — sending is the
    seam's job."""
    if k < 1:
        raise ValueError("a round dispatches at least one packet")
    if k > len(lenses):
        raise ValueError(f"k={k} exceeds the {len(lenses)} lenses available")
    return [
        compose_packet(item, prompt, lens, round_, model=model, project=project)
        for lens in lenses[:k]
    ]


# --------------------------------------------------------------------------- #
# The ledger — append-only, two row shapes, one spine
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Row:
    """One ledger row. ``data`` is merged flat into the record on write, the
    on-disk shape synthetics-genesis uses; the spine keys are reserved."""

    row_id: str
    item_id: str
    round: int
    kind: str
    subject: str
    observed_by: str
    supersedes: tuple[str, ...] = ()
    data: Mapping[str, Any] = field(default_factory=dict)

    def as_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "row_id": self.row_id,
            "item_id": self.item_id,
            "round": self.round,
            "kind": self.kind,
            "subject": self.subject,
            "observed_by": self.observed_by,
        }
        if self.supersedes:
            record["supersedes"] = list(self.supersedes)
        for key, value in self.data.items():
            if key in SPINE or key == "supersedes":
                raise ValueError(f"row data may not shadow the spine key {key!r}")
            record[key] = value
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Row:
        """Rehydrate. The round key is read as an integer or rejected — the
        original compared a string state against an int and degraded to a silent
        ``false``, which reported the trigger's own deadness as a clean
        negative."""
        missing = [k for k in SPINE if k not in record]
        if missing:
            raise ValueError(f"row missing spine keys: {missing}")
        rnd = record["round"]
        if isinstance(rnd, bool) or not isinstance(rnd, int):
            raise ValueError(f"round must be an integer, got {rnd!r}")
        data = {k: v for k, v in record.items() if k not in SPINE and k != "supersedes"}
        return cls(
            row_id=str(record["row_id"]),
            item_id=str(record["item_id"]),
            round=rnd,
            kind=str(record["kind"]),
            subject=str(record["subject"]),
            observed_by=str(record["observed_by"]),
            supersedes=tuple(record.get("supersedes", ()) or ()),
            data=data,
        )


def row_errors(record: Mapping[str, Any], known_ids: Iterable[str] = ()) -> list[str]:
    """Validate one record against the rows already banked. Errors, empty clean."""
    errs: list[str] = []
    try:
        row = Row.from_record(record)
    except ValueError as e:
        return [str(e)]
    if not row.row_id:
        errs.append("row_id is empty")
    if not row.item_id:
        errs.append(f"{row.row_id}: item_id is empty")
    if row.round < 0:
        errs.append(f"{row.row_id}: round {row.round} is negative")
    if row.kind not in ROW_KINDS:
        errs.append(f"{row.row_id}: kind {row.kind!r} not in {ROW_KINDS}")
    if not row.subject.strip():
        errs.append(f"{row.row_id}: subject is empty")
    if not row.observed_by.strip():
        errs.append(f"{row.row_id}: observed_by is empty")
    ids = set(known_ids)
    for target in row.supersedes:
        if target not in ids:
            errs.append(f"{row.row_id}: supersedes {target!r}, which no earlier row carries")
    if row.kind == "withdrawal":
        if not row.supersedes:
            errs.append(f"{row.row_id}: a withdrawal names no superseded row")
        if not any(row.subject.startswith(tag) for tag in WITHDRAWAL_TAGS):
            errs.append(f"{row.row_id}: withdrawal subject lacks an uppercase verb tag")
        if row.data.get("scope") not in WITHDRAWAL_SCOPES:
            errs.append(f"{row.row_id}: withdrawal scope {row.data.get('scope')!r} "
                        f"not in {WITHDRAWAL_SCOPES}")
    if row.kind == "transition":
        absent = [k for k in SIX_ITEMS if not str(row.data.get(k, "")).strip()]
        if absent:
            errs.append(f"{row.row_id}: transition row missing the six items: {absent}")
    if row.kind == "residue":
        residue = row.data.get("residue")
        if not isinstance(residue, Mapping):
            errs.append(f"{row.row_id}: residue row carries no residue record")
        else:
            errs.extend(f"{row.row_id}: {e}" for e in sx.check_residue_rows([dict(residue)]))
    return errs


def validate_rows(records: Sequence[Mapping[str, Any]]) -> list[str]:
    """Validate a whole ledger: unique ids, every ``supersedes`` target existing
    EARLIER in the file, and each row's own shape. The validator the original
    lacks — synthetics-genesis practises the discipline and enforces none of it."""
    errs: list[str] = []
    seen: set[str] = set()
    for record in records:
        rid = str(record.get("row_id", ""))
        if rid in seen:
            errs.append(f"{rid}: duplicate row_id")
        errs.extend(row_errors(record, seen))
        if rid:
            seen.add(rid)
    return errs


def check_append_only(before: Sequence[str], after: Sequence[str]) -> list[str]:
    """Append-only across commits: ``after`` opens with ``before``, byte for byte.
    A mutated or dropped earlier line is named with its index."""
    errs: list[str] = []
    if len(after) < len(before):
        errs.append(f"ledger shrank: {len(before)} lines -> {len(after)}")
    for i, line in enumerate(before[: len(after)]):
        if after[i] != line:
            errs.append(f"line {i} was rewritten")
    return errs


class Ledger:
    """The append-only JSONL ledger. Every candidate, residue, withdrawal and
    submission is a new line; nothing is ever rewritten."""

    def __init__(self, path: str | Path = GENESIS_PATH, *, prefix: str = "S",
                 observed_by: str = OBSERVED_BY) -> None:
        self.path = Path(path)
        self.prefix = prefix
        self.observed_by = observed_by
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = self.records()
        self._count = len(records)
        self._ids = {str(r.get("row_id", "")) for r in records}

    def raw_lines(self) -> list[str]:
        if not self.path.is_file():
            return []
        return [ln for ln in self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def records(self) -> list[dict[str, Any]]:
        return [json.loads(ln) for ln in self.raw_lines()]

    def rows(self) -> list[Row]:
        return [Row.from_record(r) for r in self.records()]

    def next_row_id(self) -> str:
        return f"{self.prefix}{self._count + 1:04d}"

    def append(self, *, item_id: str, round_: int, kind: str, subject: str,
               observed_by: str | None = None, supersedes: Sequence[str] = (),
               **data: Any) -> Row:
        """Append one row. Validated before it is written — a row that would make
        the ledger unreadable never reaches the file."""
        row = Row(
            row_id=self.next_row_id(),
            item_id=item_id,
            round=round_,
            kind=kind,
            subject=subject,
            observed_by=observed_by or self.observed_by,
            supersedes=tuple(supersedes),
            data=data,
        )
        record = row.as_record()
        if errs := row_errors(record, self._ids):
            raise ValueError(f"refusing to append an invalid row: {errs}")
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        self._count += 1
        self._ids.add(row.row_id)
        return row

    def validate(self) -> list[str]:
        return validate_rows(self.records())


def withdraw(ledger: Ledger, superseded: Sequence[str], *, item_id: str, round_: int,
             subject: str, scope: str, **data: Any) -> Row:
    """Bank a withdrawal as a NEW row naming the superseded ids. Never an
    overwrite: the withdrawn row stays exactly as it was written, and the
    withdrawal is reachable from the file's own order."""
    if not any(subject.startswith(tag) for tag in WITHDRAWAL_TAGS):
        raise ValueError(
            f"a withdrawal subject opens with an uppercase verb tag, one of {WITHDRAWAL_TAGS}")
    if scope not in WITHDRAWAL_SCOPES:
        raise ValueError(f"withdrawal scope {scope!r} not in {WITHDRAWAL_SCOPES}")
    return ledger.append(item_id=item_id, round_=round_, kind="withdrawal",
                         subject=subject, supersedes=tuple(superseded), scope=scope, **data)


# --------------------------------------------------------------------------- #
# The convergence organ — NEW, from append-only rows alone
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ConvergenceRecord:
    """What the rows say about one item's convergence. Every field is a function
    of the append-only rows and nothing else — no live state, no side file."""

    item_id: str
    converged: bool
    signal: str
    first_round: int | None
    best_row_id: str
    best_bin: Bin | None
    best_formula: str
    distinct_verified: int
    promotions: tuple[dict[str, Any], ...] = ()
    withdrawn: tuple[str, ...] = ()

    def as_record(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "converged": self.converged,
            "signal": self.signal,
            "first_round": self.first_round,
            "best_row_id": self.best_row_id,
            "best_bin": self.best_bin.value if self.best_bin else None,
            "best_formula": self.best_formula,
            "distinct_verified": self.distinct_verified,
            "promotions": [dict(p) for p in self.promotions],
            "withdrawn": list(self.withdrawn),
        }


def _bin_of(row: Row) -> Bin | None:
    raw = row.data.get("bin")
    return Bin(raw) if raw else None


def _rank(row: Row) -> int:
    b = _bin_of(row)
    return BIN_RANK[b] if b else 0


def select_best(rows: Sequence[Row]) -> Row | None:
    """The item's submission of record among its surviving verified rows.

    Ranked by BIN and then by the earliest round that reached it. There is no δ
    term, no length term and no nBDM anywhere on this path: bin promotion is a
    10-100x φ move, δ is a density a shorter program raises, and an objective
    that read δ would be optimizing the instrument that scores us."""
    admitted = [r for r in rows if r.data.get("gate_admitted") and _bin_of(r)]
    if not admitted:
        return None
    return min(admitted, key=lambda r: (-_rank(r), r.round, r.row_id))


def _superseded_ids(rows: Sequence[Row], *, scope: str | None = None) -> set[str]:
    """Ids some withdrawal row names. ``scope`` narrows to one kind of taking-back
    — only a ``verification`` withdrawal denies that the byte-compare happened."""
    out: set[str] = set()
    for row in rows:
        if row.kind == "withdrawal" and (scope is None or row.data.get("scope") == scope):
            out.update(row.supersedes)
    return out


def convergence(rows: Sequence[Row] | Sequence[Mapping[str, Any]], item_id: str) -> ConvergenceRecord:
    """The convergence record for one item, computed from rows alone.

    The trigger is φ-relevant progress — a verified-correct model found, or an
    existing verified model promoted to a better bin — never residue shrinkage:
    φ is a step function at correctness, so an item diverging at index 11 scores
    what one diverging at index 1 scores.

    Three corrections to the organ this replaces are load-bearing: rows are
    round-stamped and append-only (a non-integer round raises, in
    :py:meth:`Row.from_record`, rather than silently comparing unequal);
    withdrawn rows are excluded by the file's own ``supersedes`` pointers, by
    SCOPE — a promotion retires an answer, only a ``verification`` withdrawal
    denies the byte-compare and can un-converge the item; and
    verified rows are deduplicated by candidate id before any count, so one
    candidate banked twice cannot satisfy a threshold on its own."""
    parsed = [r if isinstance(r, Row) else Row.from_record(r) for r in rows]
    mine = [r for r in parsed if r.item_id == item_id]
    dead = _superseded_ids(parsed)
    denied = _superseded_ids(parsed, scope="verification")
    withdrawn = tuple(r.row_id for r in mine if r.row_id in dead)

    verified: list[Row] = []
    seen_candidates: set[str] = set()
    for row in sorted((r for r in mine if r.kind == "verified" and r.row_id not in denied),
                      key=lambda r: (r.round, r.row_id)):
        cid = str(row.data.get("candidate_id") or row.row_id)
        if cid in seen_candidates:
            continue
        seen_candidates.add(cid)
        verified.append(row)

    if not verified:
        return ConvergenceRecord(item_id, False, "", None, "", None, "", 0,
                                 withdrawn=withdrawn)

    promotions: list[dict[str, Any]] = []
    best = verified[0]
    for row in verified[1:]:
        if _rank(row) > _rank(best):
            promotions.append({
                "round": row.round,
                "from_bin": (_bin_of(best).value if _bin_of(best) else None),
                "to_bin": (_bin_of(row).value if _bin_of(row) else None),
                "row_id": row.row_id,
            })
            best = row
    chosen = select_best([r for r in verified if r.row_id not in dead]) or best
    signal = SIGNAL_PROMOTED if promotions else SIGNAL_FOUND
    return ConvergenceRecord(
        item_id=item_id,
        converged=True,
        signal=signal,
        first_round=verified[0].round,
        best_row_id=chosen.row_id,
        best_bin=_bin_of(chosen),
        best_formula=str(chosen.data.get("formula", "")),
        distinct_verified=len(verified),
        promotions=tuple(promotions),
        withdrawn=withdrawn,
    )


# --------------------------------------------------------------------------- #
# Budget — allocated, not merely spent
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Budget:
    """The campaign's round budget. ``total_rounds`` is the pool; per item the
    ceiling is ``max_rounds_per_item``, and the allocator keeps one round in
    reserve for every item not yet attempted."""

    total_rounds: int
    max_rounds_per_item: int = MAX_ROUNDS_PER_ITEM
    abandon_threshold: float = ABANDON_P_THRESHOLD

    def __post_init__(self) -> None:
        if self.total_rounds < 1:
            raise ValueError("the campaign needs at least one round")
        if self.max_rounds_per_item < 1:
            raise ValueError("an item needs at least one round")
        if not 0.0 <= self.abandon_threshold <= 1.0:
            raise ValueError("the abandonment threshold is a probability")


def p_closure(advances: int, rounds_used: int, rounds_left: int) -> float:
    """Estimated P(closure within the rounds left).

    A Laplace-smoothed per-round hazard from the item's own history — an ADVANCE
    is a round that reproduced strictly more of the sequence than any round
    before it — compounded over the rounds remaining. Deliberately crude and
    deliberately stated: the point of the estimator is that abandonment is a
    preregistered arithmetic decision rather than a judgement call, and an item
    that has advanced keeps its budget while one that has not loses it."""
    if rounds_left <= 0:
        return 0.0
    if advances < 0 or rounds_used < 0:
        raise ValueError("counts are non-negative")
    hazard = (advances + 1) / (rounds_used + 2)
    return 1.0 - (1.0 - hazard) ** rounds_left


def allocate(pool: int, items_remaining: int, max_rounds_per_item: int) -> int:
    """Rounds the next item may spend: its ceiling, capped so that every item
    still unattempted keeps one round of the pool — but never below one round
    while the pool has anything in it, so a thin pool starves the tail rather
    than the head. Rounds an abandoned item did not spend fall back into the
    pool and are spent by the items after it, which is the whole point of the
    rule: budget lands on unattempted items rather than on an item that will
    not close."""
    if items_remaining < 1:
        raise ValueError("no items remaining")
    if pool <= 0:
        return 0
    reserve = items_remaining - 1
    return max(1, min(max_rounds_per_item, pool - reserve))


# --------------------------------------------------------------------------- #
# Capability gaps
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CapabilityGap:
    """Six fields, ported. ``why_iteration_cannot`` is typed and
    ``budget-exhausted`` is its own member: an item we merely stopped is not an
    item no iteration can close, and merging them inflates the residual frontier."""

    item_id: str
    gap: str
    what_organ_would_close_it: str
    why_iteration_cannot: str
    first_seen_round: int
    evidence: str

    def __post_init__(self) -> None:
        if self.why_iteration_cannot not in WHY_ITERATION_CANNOT:
            raise ValueError(
                f"why_iteration_cannot {self.why_iteration_cannot!r} not in {WHY_ITERATION_CANNOT}")

    def as_record(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "gap": self.gap,
            "what_organ_would_close_it": self.what_organ_would_close_it,
            "why_iteration_cannot": self.why_iteration_cannot,
            "first_seen_round": self.first_seen_round,
            "evidence": self.evidence,
        }

    def as_row_data(self) -> dict[str, Any]:
        """The record without ``item_id`` — the ledger row carries that on the
        spine, and a row may not shadow a spine key."""
        return {k: v for k, v in self.as_record().items() if k != "item_id"}


def write_capability_gaps(gaps: Iterable[CapabilityGap],
                          path: str | Path = CAPABILITY_GAPS_PATH) -> Path:
    """Append the gaps. Append-only, like everything else in the campaign."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for gap in gaps:
            fh.write(json.dumps(gap.as_record(), ensure_ascii=False, sort_keys=True) + "\n")
    return p


# --------------------------------------------------------------------------- #
# The per-item loop
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ItemResult:
    """One item's whole run, as data."""

    item_id: str
    sequence: str
    rounds_used: int
    closed: bool
    abandoned: bool
    convergence: ConvergenceRecord
    answer: str
    bin: Bin | None
    advances: int
    residues: tuple[dict[str, Any], ...] = ()
    gap: CapabilityGap | None = None

    @property
    def submitted(self) -> bool:
        """A model reproduces the item AND its formula passed the submission
        gate. A verified program whose formula is refused is banked as evidence
        and is not a submission."""
        return self.bin is not None and bool(self.answer)

    def as_record(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "rounds_used": self.rounds_used,
            "closed": self.closed,
            "abandoned": self.abandoned,
            "submitted": self.submitted,
            "answer": self.answer,
            "bin": self.bin.value if self.bin else None,
            "advances": self.advances,
            "convergence": self.convergence.as_record(),
            "gap": self.gap.as_record() if self.gap else None,
        }


def _account_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (row.get("class"), row.get("index"), row.get("got"), row.get("expected"))


def _merge_account(account: Sequence[dict[str, Any]],
                   fresh: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """The residue account: deduplicated by the divergence itself, capped at the
    bench's row cap, newest last. Deduplication is what makes 'no new residue' a
    real observation rather than an artefact of re-running the same lens."""
    merged = list(account)
    seen = {_account_key(r) for r in merged}
    for row in fresh:
        key = _account_key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged[-MAX_ACCOUNT_ROWS:]


def _depth_of(residue: Mapping[str, Any] | None, n_terms: int) -> int:
    """How much of the sequence a candidate reproduced: the first divergence
    index, or the whole item when it verified."""
    if residue is None:
        return n_terms
    idx = residue.get("index")
    return int(idx) if isinstance(idx, int) else 0


def _gap_for(item: Item, result_closed: bool, submitted: bool, abandoned: bool,
             rounds_used: int, residues: Sequence[Mapping[str, Any]],
             override: str | None = None) -> CapabilityGap:
    """Route an unsubmitted item to the residual frontier, typed.

    Budget-exhausted is separate by construction: an item the allocation rule
    dropped, or one that simply ran out of rounds, says so and is not counted
    among the items no iteration can close."""
    classes = sorted({str(r.get("class")) for r in residues}) or ["none"]
    if override:
        why = override
    elif result_closed and not submitted:
        why = "capability"
    else:
        why = "budget-exhausted"
    gap = (
        f"item {item.item_id}: a verified model exists but no gate-admissible formula"
        if result_closed and not submitted
        else f"item {item.item_id}: no candidate reproduced the sequence"
    )
    organ = (
        "a formula stating the same model without stored literal data"
        if result_closed and not submitted
        else "a lens the loop does not carry, or rounds the campaign did not have"
    )
    evidence = (
        f"{rounds_used} round(s); residue classes observed: {', '.join(classes)}"
        + ("; abandoned by the allocation rule" if abandoned else "")
    )
    return CapabilityGap(
        item_id=item.item_id,
        gap=gap,
        what_organ_would_close_it=organ,
        why_iteration_cannot=why,
        first_seen_round=0,
        evidence=evidence,
    )


def run_item(
    item: Item,
    proposer: Proposer,
    *,
    ledger: Ledger,
    max_rounds: int = MAX_ROUNDS_PER_ITEM,
    k: int = DEFAULT_K,
    lenses: Sequence[str] = LENSES,
    timeout: float = sx.EXEC_TIMEOUT_S,
    abandon_threshold: float = ABANDON_P_THRESHOLD,
    model: str | None = None,
    project: registry.Project | None = None,
    gap_reason: str | None = None,
) -> ItemResult:
    """Run one item's genesis loop: P0, then rounds until it converges, its bin
    can no longer improve, the allocation rule drops it, or the rounds run out.

    Every candidate, every typed residue, every withdrawal and the transition
    rows all append to ``ledger``. Nothing is ever rewritten, so the convergence
    record stays recomputable from the file alone."""
    n_terms = len(item.terms)
    prompt = prompt_zero(item)
    account: list[dict[str, Any]] = []
    best_depth = 0
    advances = 0
    rounds_used = 0
    abandoned = False
    best_row: Row | None = None
    all_residues: list[dict[str, Any]] = []

    for round_ in range(max_rounds):
        rounds_left = max_rounds - round_
        if round_ > 0 and best_row is None:
            p = p_closure(advances, rounds_used, rounds_left)
            if p < abandon_threshold:
                abandoned = True
                ledger.append(
                    item_id=item.item_id, round_=round_, kind="abandonment",
                    subject=f"item {item.item_id} abandoned: P(closure) below the threshold",
                    p_closure=round(p, 6), threshold=abandon_threshold,
                    advances=advances, rounds_used=rounds_used, rounds_left=rounds_left,
                )
                break
        rounds_used += 1
        round_residues: list[dict[str, Any]] = []
        round_depth = 0
        verified_before = best_row

        for packet in compose_round(item, prompt, round_, lenses=lenses, k=k,
                                    model=model, project=project):
            for i, proposal in enumerate(proposer(packet)):
                cid = f"{item.item_id}-r{round_}-{packet.lens}-{i}"
                verdict = sx.verify_candidate(proposal.source, item.sequence, timeout=timeout)
                ledger.append(
                    item_id=item.item_id, round_=round_, kind="candidate",
                    subject=f"{packet.lens}: candidate {cid} executed and byte-compared",
                    candidate_id=cid, lens=packet.lens, model=packet.model,
                    passed=verdict.passed, execution=verdict.execution,
                    formula=proposal.formula, note=proposal.note,
                )
                round_depth = max(round_depth, _depth_of(verdict.residue, n_terms))
                if not verdict.passed:
                    residue = dict(verdict.residue or {})
                    residue.update({"round": round_, "lens": packet.lens, "candidate_id": cid})
                    ledger.append(
                        item_id=item.item_id, round_=round_, kind="residue",
                        subject=f"{packet.lens}: {residue.get('class')} at index {residue.get('index')}",
                        candidate_id=cid, lens=packet.lens, residue=residue,
                    )
                    round_residues.append(residue)
                    all_residues.append(residue)
                    continue

                decision = submission_gate.gate(proposal.formula, item.sequence)
                bin_ = classify(proposal.formula, item.sequence, correct=True).bin if decision.admitted else None
                row = ledger.append(
                    item_id=item.item_id, round_=round_, kind="verified",
                    subject=f"{packet.lens}: candidate {cid} reproduces the sequence byte for byte",
                    candidate_id=cid, lens=packet.lens, source=proposal.source,
                    formula=proposal.formula, gate_admitted=decision.admitted,
                    gate=decision.as_record(), bin=bin_.value if bin_ else None,
                )
                # A verified program whose formula the gate refuses ranks ZERO: it
                # is banked as evidence and cannot be the submission of record, so
                # replacing it later with a gate-admitted formula is a real bin
                # promotion (0 -> the abstraction bin), not a cosmetic one.
                if best_row is None:
                    best_row = row
                elif _rank(row) > _rank(best_row):
                    superseded = best_row
                    best_row = row
                    ledger.append(
                        item_id=item.item_id, round_=round_, kind="promotion",
                        subject=(f"{cid} promoted the item from "
                                 f"{superseded.data.get('bin') or 'unsubmittable'} to {bin_.value}"),
                        candidate_id=cid, from_bin=superseded.data.get("bin"),
                        to_bin=bin_.value, from_row=superseded.row_id,
                    )
                    withdraw(
                        ledger, [superseded.row_id], item_id=item.item_id, round_=round_,
                        subject=(f"SUPERSEDED: {superseded.row_id}'s submission of record for "
                                 f"{item.item_id}, replaced by {row.row_id} on bin promotion"),
                        scope="submission-of-record", replaced_by=row.row_id,
                    )

        if round_depth > best_depth:
            best_depth = round_depth
            advances += 1

        if best_row is not None and _rank(best_row) >= TOP_BIN_RANK:
            break

        merged = _merge_account(account, round_residues)
        promoted = best_row is not verified_before
        if merged != account or promoted:
            prior_classes = sorted({str(r.get("class")) for r in account}) or ["none"]
            fresh_classes = sorted({str(r.get("class")) for r in round_residues
                                    if _account_key(r) not in {_account_key(a) for a in account}})
            account = merged
            prompt = rewrite_prompt(item, account, best_row.data if best_row else None)
            ledger.append(
                item_id=item.item_id, round_=round_, kind="transition",
                subject=f"P{round_} -> P{round_ + 1}",
                prior_representation=(f"P{round_}: {len(account)} residue row(s) carried, "
                                      f"classes {', '.join(prior_classes)}"),
                evidence_explained=(f"{best_depth} of {n_terms} terms reproduced by the best "
                                    f"candidate so far"),
                residue_unabsorbed=(", ".join(f"{r.get('class')}@{r.get('index')}"
                                              for r in account) or "none"),
                change_introduced=(f"P{round_ + 1} rewritten from P0 verbatim plus "
                                   f"{len(account)} typed residue row(s)"),
                new_closure=(f"verified model in bin {best_row.data.get('bin')}"
                             if best_row else "none: no candidate reproduced the sequence"),
                new_residue=", ".join(fresh_classes) or "none",
                prompt=prompt,
            )
        else:
            ledger.append(
                item_id=item.item_id, round_=round_, kind="no-rewrite",
                subject=f"P{round_} stands: the round produced no residue the account lacks",
                account_rows=len(account),
            )

    banked = ledger.rows()
    record = convergence(banked, item.item_id)
    dead = _superseded_ids(banked)
    chosen = select_best([r for r in banked
                          if r.item_id == item.item_id and r.kind == "verified"
                          and r.row_id not in dead])
    answer = str(chosen.data.get("formula", "")) if chosen else ""
    bin_ = _bin_of(chosen) if chosen else None
    closed = record.converged
    submitted = bin_ is not None and bool(answer)
    gap = None
    if not submitted:
        gap = _gap_for(item, closed, submitted, abandoned, rounds_used, all_residues, gap_reason)
        ledger.append(
            item_id=item.item_id, round_=max(rounds_used - 1, 0), kind="gap",
            subject=f"item {item.item_id} routed to capability-gaps ({gap.why_iteration_cannot})",
            **gap.as_row_data(),
        )
    return ItemResult(
        item_id=item.item_id,
        sequence=item.sequence,
        rounds_used=rounds_used,
        closed=closed,
        abandoned=abandoned,
        convergence=record,
        answer=answer,
        bin=bin_,
        advances=advances,
        residues=tuple(all_residues),
        gap=gap,
    )


# --------------------------------------------------------------------------- #
# Submission — the GLOBAL post-run decision
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Submission:
    """The run's submission set and its φ. ``rule`` is the preregistered rule the
    set was built under, carried so a reader never has to infer it."""

    rule: str
    rows: tuple[phi.LedgerRow, ...]
    score: phi.Score
    submitted: tuple[str, ...]
    withheld: tuple[str, ...]

    def as_record(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "score": self.score.as_record(),
            "submitted": list(self.submitted),
            "withheld": list(self.withheld),
            "rows": [r.as_record() for r in self.rows],
        }


def submission_answers(results: Sequence[ItemResult]) -> list[phi.Answer]:
    """The preregistered set: EVERY item, always, best available bin, no
    selection — the authors' one-answer-per-sequence protocol.

    An unclosed item is an INCORRECT row with an empty answer, never a dropped
    row: the incorrect bin carries no δ but is counted in the denominator, so
    dropping it would inflate every ρ. Abstention is not conservative — the
    incorrect bin never enters φ, so abstaining and answering wrongly both
    score 0."""
    answers = []
    for result in results:
        if result.submitted and result.bin is not None:
            answers.append(phi.Answer(result.item_id, result.sequence, result.answer, result.bin))
        else:
            answers.append(phi.Answer(result.item_id, result.sequence, "", Bin.INCORRECT))
    return answers


def global_submission(results: Sequence[ItemResult], *,
                      expected_n: int | None = None,
                      rule: str = SUBMISSION_RULE) -> Submission:
    """φ over the whole run — a GLOBAL decision, because a bin's contribution is
    quadratic in bin size and harmonic in δ, and a per-item gate cannot express
    what one more answer does to the total."""
    if rule != SUBMISSION_RULE:
        raise ValueError(
            f"submission rule {rule!r} is not the preregistered {SUBMISSION_RULE!r}; "
            "a selective rule must be declared before the run")
    answers = submission_answers(results)
    rows = phi.ledger_rows(answers)
    score = phi.score(rows, expected_n=expected_n)
    submitted = tuple(r.item_id for r in results if r.submitted)
    withheld = tuple(r.item_id for r in results if not r.submitted)
    return Submission(rule=rule, rows=tuple(rows), score=score,
                      submitted=submitted, withheld=withheld)


def compare_submission_sets(rows: Sequence[phi.LedgerRow],
                            subsets: Mapping[str, Iterable[str]]) -> dict[str, phi.Score]:
    """φ for each named submission set, through :py:func:`phi.from_ledger`.

    An item outside a set is re-binned INCORRECT rather than dropped — withholding
    an answer does not remove the item from the suite. This exists to DISCLOSE the
    harmonic-mean fragility (adding a correct-but-low-δ answer to a bin can lower
    φ; break-even δ is about half the bin mean), not to pick: the preregistered
    rule submits everything, and any selective rule must be declared before the
    run or a skeptic reads it as metric gaming."""
    out: dict[str, phi.Score] = {}
    for name, ids in subsets.items():
        keep = set(ids)
        records = [
            (r if r.item_id in keep else replace(r, bin=Bin.INCORRECT)).as_record()
            for r in rows
        ]
        out[name] = phi.from_ledger(records, expected_n=None)
    return out


def phi_rows(rows: Sequence[Row] | Sequence[Mapping[str, Any]]) -> list[phi.LedgerRow]:
    """The φ ledger recovered from the genesis rows alone — the submission rows
    carry the answer, the bin and both nBDM values, so the run's score survives
    as arithmetic over its own append-only file."""
    parsed = [r if isinstance(r, Row) else Row.from_record(r) for r in rows]
    return [
        phi.LedgerRow.from_record({
            "item_id": row.item_id,
            "answer": row.data.get("answer", ""),
            "bin": row.data.get("bin"),
            "nbdm_input": row.data.get("nbdm_input"),
            "nbdm_answer": row.data.get("nbdm_answer"),
        })
        for row in parsed if row.kind == "submission"
    ]


# --------------------------------------------------------------------------- #
# The campaign
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CampaignResult:
    results: tuple[ItemResult, ...]
    rounds_spent: int
    gaps: tuple[CapabilityGap, ...]
    submission: Submission | None

    def as_record(self) -> dict[str, Any]:
        return {
            "rounds_spent": self.rounds_spent,
            "items_attempted": sum(1 for r in self.results if r.rounds_used > 0),
            "items_closed": sum(1 for r in self.results if r.closed),
            "rounds_per_closed_item": (
                self.rounds_spent / max(1, sum(1 for r in self.results if r.closed))),
            "results": [r.as_record() for r in self.results],
            "gaps": [g.as_record() for g in self.gaps],
            "submission": self.submission.as_record() if self.submission else None,
        }


def run_campaign(
    items: Sequence[Item],
    proposer: Proposer,
    *,
    ledger: Ledger,
    budget: Budget | None = None,
    k: int = DEFAULT_K,
    lenses: Sequence[str] = LENSES,
    timeout: float = sx.EXEC_TIMEOUT_S,
    model: str | None = None,
    score: bool = True,
    expected_n: int | None = None,
    gap_reasons: Mapping[str, str] | None = None,
) -> CampaignResult:
    """Run every item, then decide submission GLOBALLY.

    The allocator keeps one round of the pool in reserve for each item not yet
    attempted, and rounds an abandoned item did not spend fall back into the pool
    for the items after it — the whole point of the rule is that budget lands on
    unattempted items rather than on an item that will not close."""
    if not items:
        raise ValueError("a campaign needs at least one item")
    budget = budget or Budget(total_rounds=len(items) * MAX_ROUNDS_PER_ITEM)
    project = _project()
    pool = budget.total_rounds
    results: list[ItemResult] = []
    for i, item in enumerate(items):
        allowed = allocate(pool, len(items) - i, budget.max_rounds_per_item)
        if allowed < 1:
            result = ItemResult(
                item_id=item.item_id, sequence=item.sequence, rounds_used=0, closed=False,
                abandoned=True,
                convergence=ConvergenceRecord(item.item_id, False, "", None, "", None, "", 0),
                answer="", bin=None, advances=0,
                gap=_gap_for(item, False, False, True, 0, (), "budget-exhausted"),
            )
            ledger.append(item_id=item.item_id, round_=0, kind="gap",
                          subject=f"item {item.item_id} never attempted: the pool was spent",
                          **result.gap.as_row_data())
            results.append(result)
            continue
        result = run_item(
            item, proposer, ledger=ledger, max_rounds=allowed, k=k, lenses=lenses,
            timeout=timeout, abandon_threshold=budget.abandon_threshold, model=model,
            project=project, gap_reason=(gap_reasons or {}).get(item.item_id),
        )
        pool -= result.rounds_used
        results.append(result)

    gaps = tuple(r.gap for r in results if r.gap is not None)
    submission = None
    if score:
        submission = global_submission(results, expected_n=expected_n)
        for row in submission.rows:
            record = row.as_record()
            ledger.append(
                item_id=row.item_id, round_=0, kind="submission",
                subject=f"submission of record for {row.item_id} ({row.bin.value})",
                rule=SUBMISSION_RULE, **{k_: v for k_, v in record.items() if k_ != "item_id"},
            )
    return CampaignResult(
        results=tuple(results),
        rounds_spent=budget.total_rounds - pool,
        gaps=gaps,
        submission=submission,
    )
