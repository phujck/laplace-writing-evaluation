"""The author-proxy adjudicator — the organ that CLOSES forks instead of parking them.

His rulings tonight are this module's whole spine. First: *"I think you often use
forks as an excuse not to finish… in basically every case you know the answer"* —
so the proxy DECIDES. Then the correction on the shape of that autonomy: *"it's no
good if I hold the veto… Autonomy is autonomy not autonomy except"* — so the proxy
decides **and banks**, with NO veto field. Correction is retrospective through the
ledger (append a ``kind:"contest"`` record), never prospective through a veto queue.

Two moving parts, no model call anywhere:

- :func:`assemble_decision_frame` gathers the minimal-sufficient frame a dispatched
  JUDGE consumes to rule on one question/fork: the decision-profile organs (which
  had been read by zero decision code — ``EIGEN_AUTHOR.md`` was only ever classified
  as seal content by ``identity_lens``; this is where they get wired in), the
  harvested ``(his, <date>)`` ruling corpus, the prior verdicts, the RECALLED slice of
  his own live rulings ranked against the question (the return leg — see
  :mod:`laplace.engine.ruling_recall`), and the fork's own rows. It never judges; it builds
  the frame and rings back up.
- :func:`bank_ruling` / :func:`contest_ruling` are the ONLY writes: append-only,
  to ``proxy_verdicts.jsonl`` at the repo root, mirroring ``pipeline.ledger``'s
  append idiom. A verdict is never edited in place — a contest is a new record.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path

# Reuse the ONE ledger engine's IO where it's importable (author_proxy lives inside
# the package, so no src-path bootstrap is needed); fall back to a local tolerant
# read/append if the pipeline import chain is unavailable in some thin context.
try:
    from laplace.pipeline.ledger import append_jsonl as _append_jsonl
    from laplace.pipeline.ledger import read_jsonl as _read_jsonl
except Exception:  # pragma: no cover - defensive: the fallback matches the engine's shape
    def _read_jsonl(path: Path | str) -> list[dict]:
        p = Path(path)
        if not p.is_file():
            return []
        out: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return out

    def _append_jsonl(path: Path | str, record: dict) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


LEDGER_NAME = "proxy_verdicts.jsonl"

# The decision-profile organs — his read of himself, in four registers. Located by
# pattern so a version bump (…_v2, a newer psych date) is picked up automatically.
_PROFILE_ORGANS = (
    ("eigen_author", ("EIGEN_AUTHOR.md",)),
    ("mini_conceptric", ("profiles/gerard_mini_conceptric*.json",
                         "profiles/*mini_conceptric*.json")),
    ("psych_profile", ("profiles/GERARD_PSYCH*.md", "profiles/*psych*profile*.md")),
    ("voice_profile", ("*gerard-technical-voice-profile*.md",
                       "DESIGN_*technical-voice-profile*.md")),
)

# A durable ruling line: "(his, 2026-06-08 …)" / "(his 2026-07-11)" — the author's
# banked calls scattered through the root corpus.
_RULING_RE = re.compile(r"\(his,?\s+20\d\d")
_DATE_RE = re.compile(r"20\d\d(?:-\d\d-\d\d)?")

_LIVE_MARKER = "\U0001f534"  # 🔴 — OPEN_STACK's live status legend

# ---- the fusion organ: the FORM STORES as the frame's THIRD input --------------
# SCOUT_2026-07-16 line 57 / line 5: THE ADJUDICATION PERSONA IS THE REVOICING
# PERSONA. The same profile-organ-wearing judge that closes a parked STRUCTURAL fork
# rules "he'd respine/demote/reorder this" — and the evidence that makes that ruling
# his structural VOICE rather than vibes is the author's own published section
# architecture and spine ladder. For a STRUCTURAL question the frame retrieves the
# k-nearest authored FORM exemplars from ``section_architecture`` (normalized_job /
# arc) and ``spine_chain`` (ladder_move) via the ONE gate-and-dial-gated retrieval
# wire (``stage_retrieval.build_form_channel``) and carries the FORM-EXEMPLARS
# envelope as evidence. Dial-gated like every lens: a store disabled (or absent) is a
# HONEST ABSENCE, not a crash — the frame records presence/absence per store so the
# judge (and the audit) know exactly which structural evidence was in the room.
_STRUCTURAL_STORES = ("section_architecture", "spine_chain")

# A question is STRUCTURAL when it turns on section/spine SHAPE — the vocabulary the
# projection-intent ops (evolution_consumer._VERB_TO_PROPOSED_OP) and the pre-
# projection conformance pass speak. Matched loosely (word-ish) so a fork phrased in
# his register ("does he respine s4", "demote the estimates section") triggers the
# structural evidence; a non-structural taste call (deslop/naming/essence) does not,
# so those decisions never pay the retrieval cost or carry irrelevant evidence.
_STRUCTURAL_RE = re.compile(
    r"\b(respine|re-spine|spine|ladder|demote|promote|reorder|re-order|"
    r"reorg|restructure|re-structure|structural|section[- ]?shape|section[- ]?arc|"
    r"\barc\b|resequence|re-sequence|split|merge|cut|remove|excise|reopen|"
    r"restart|section\b|sections\b|subsection)",
    re.IGNORECASE,
)


def is_structural_question(question: str) -> bool:
    """True when ``question`` turns on section/spine SHAPE (the projection-intent op
    vocabulary's register) — the gate on whether the form-store evidence is retrieved
    into the frame. A pure taste call (deslop/naming/essence) returns False, so it
    never carries structural evidence it cannot use."""
    return bool(_STRUCTURAL_RE.search(question or ""))


def build_form_exemplars(repo_root: Path | str, question: str,
                         fork_text: list[str] | None = None,
                         k: int = 3, dials: dict | None = None) -> dict:
    """The frame's THIRD input: the author's own STRUCTURAL FORM as adjudication
    evidence. For a structural ``question`` (see :func:`is_structural_question`),
    retrieve the k-nearest authored FORM exemplars from each of
    :data:`_STRUCTURAL_STORES` via the gate-and-dial-gated retrieval wire and carry
    the FORM-EXEMPLARS envelope per store. NEVER calls a model; NEVER surfaces prose
    (the wire's ``_FORM_KEYS`` whitelist makes ``embed_text`` structurally
    unreachable). Dial-gated like every lens — the frame records presence/absence
    Plainly:

      * non-structural question → ``structural=False``, each store noted
        ``"not-a-structural-question"`` (no retrieval);
      * structural + store dial OFF (the inert default) → ``served=False``,
        ``"dial-off (store not enabled)"``;
      * structural + store served → ``served=True`` with the envelope;
      * structural + store dial ON but the gate REFUSES / the store is broken
        (``SystemExit`` from the wire) → ``served=False`` with the stated refusal
        reason — the frame does not crash the decision, but the absence and its
        cause are on the record (the dial-cannot-override-the-gate law, surfaced not
        swallowed).

    The query embeds the question plus any fork rows (the whole decision OBJECT), so
    the retrieved shapes answer the fork actually parked, not just its title."""
    question = question or ""
    structural = is_structural_question(question)
    query = question
    if fork_text:
        query = (question + "\n" + "\n".join(fork_text)).strip()
    digest = "sha256:" + hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]

    stores: dict[str, dict] = {}
    served_count = 0
    if not structural:
        for store in _STRUCTURAL_STORES:
            stores[store] = {"served": False, "envelope": None,
                             "note": "not-a-structural-question"}
        return {"structural": False, "query": query, "query_digest": digest,
                "stores": stores, "served_count": 0}

    # lazy import: author_proxy is imported in thin/offline contexts (per the module
    # docstring), and the retrieval wire pulls numpy + the embed backend.
    from laplace.pipeline import stage_retrieval

    for store in _STRUCTURAL_STORES:
        try:
            envelope = stage_retrieval.build_form_channel(
                store, query, k=k, dials=dials, root=repo_root)
        except SystemExit as exc:
            # dial ON but the gate refused / the store is broken: the dial cannot
            # override the gate. Surface the honest reason; do NOT crash the frame.
            stores[store] = {"served": False, "envelope": None,
                             "note": f"refused: {exc}"}
            continue
        if envelope is None:
            stores[store] = {"served": False, "envelope": None,
                             "note": "dial-off (store not enabled)"}
        else:
            stores[store] = {"served": True, "envelope": envelope,
                             "note": f"served: k={max(1, int(k))}"}
            served_count += 1

    return {"structural": True, "query": query, "query_digest": digest,
            "stores": stores, "served_count": served_count}

#: how many of his own banked rulings the frame recalls against the question (the
#: return leg; :mod:`laplace.engine.ruling_recall`). Bounded like every other channel — the
#: relevant SLICE with provenance, never the ledger.
_RECALL_CAP = 8

REQUIRED_KEYS = (
    "id", "date", "question", "ruling", "evidence",
    "confidence", "supersedes", "unlocks", "contested",
)
CONFIDENCE_LEVELS = frozenset({"HIGH", "MEDIUM", "GENUINELY-HIS"})


def _ledger_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / LEDGER_NAME


def _newest(repo: Path, patterns: tuple[str, ...]) -> Path | None:
    hits: list[Path] = []
    for pat in patterns:
        hits.extend(p for p in repo.glob(pat) if p.is_file())
    if not hits:
        return None
    # dedupe, newest-biased: the dated/versioned name sorts last
    return sorted(set(hits), key=lambda p: p.name)[-1]


def _excerpt(path: Path, cap: int = 1400) -> str:
    """A bounded HEAD of the organ — the anchor a judge reads; the full path travels
    with it so the judge can descend rather than us flat-reading the whole file up."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[:cap]


# ------------------------------------------------------------ fork-row parsing (local)
def _fork_rows(text: str) -> list[str]:
    """OPEN_STACK's two live author-fork formats: legacy ``| F<n> | …`` table rows and
    the newer ``- **…`` 🔴 bullet forks. Borrowed shape from ``self_corpus._fork_rows``
    (kept local so this organ doesn't depend on a private helper)."""
    rows: list[str] = []
    for ln in text.splitlines():
        s = ln.lstrip()
        if s.startswith("| F") and ln.count("|") >= 3:
            rows.append(ln.strip())
        elif s.startswith("- **") and _LIVE_MARKER in ln:
            rows.append(ln.strip())
    return rows


def _fork_text(repo: Path, fork_id: str) -> list[str]:
    """Every fork row (either format) that names ``fork_id`` — the fork's own text,
    for the judge that must rule on it."""
    open_stack = repo / "OPEN_STACK.md"
    if not open_stack.is_file():
        return []
    text = open_stack.read_text(encoding="utf-8", errors="replace")
    fid = fork_id.strip()
    # match the whole fork-forms section AND any plain line naming the id (a bullet
    # fork may not itself start with "- **" once wrapped), then keep the unique rows.
    rows = [r for r in _fork_rows(text) if fid in r]
    if not rows:
        rows = [ln.strip() for ln in text.splitlines() if fid in ln]
    seen: set[str] = set()
    out: list[str] = []
    for r in rows:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


# ---------------------------------------------------------------- ruling-corpus harvest
def harvest_ruling_corpus(repo_root: Path | str, cap: int = 80) -> list[dict]:
    """Every ``(his, <date>)`` line across the root ``*.md`` corpus, newest-biased and
    capped. Each entry carries file provenance so a judge can descend to context."""
    repo = Path(repo_root)
    entries: list[dict] = []
    for md in repo.glob("*.md"):
        try:
            lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            if _RULING_RE.search(line):
                dm = _DATE_RE.search(line)
                entries.append({
                    "file": md.name,
                    "line": i,
                    "date": dm.group(0) if dm else "",
                    "text": line.strip()[:400],
                })
    # newest first; undated lines sink to the bottom
    entries.sort(key=lambda e: (e["date"], e["file"]), reverse=True)
    return entries[:cap]


# ------------------------------------------------------------------------- the frame
def assemble_decision_frame(repo_root: Path | str, question: str,
                            fork_id: str | None = None,
                            form_k: int = 3, dials: dict | None = None) -> dict:
    """Build the minimal-sufficient frame a dispatched judge consumes to rule on
    ``question`` (optionally about fork ``fork_id``). NEVER calls a model — it gathers
    the profile organs (paths + bounded excerpts), the harvested ruling corpus, the
    prior verdicts, the fork's own rows, the RECALLED slice of his own live rulings
    ranked against this question (``relevant_rulings`` + its provenance — the taste
    flywheel's return leg; :mod:`laplace.engine.ruling_recall`), AND — for a STRUCTURAL
    question — the author's own section-architecture / spine-ladder FORM exemplars as
    evidence (the fusion organ's third input; :func:`build_form_exemplars`). The form
    channel is dial-gated like every lens: absent stores are noted plainly, never a
    crash, and a non-structural question carries none
    (``form_exemplars.structural=False``). ``relevant_rulings`` may be empty — the
    provenance then states what was scanned, so an absence is on the record."""
    repo = Path(repo_root)

    profile_refs: dict[str, dict] = {}
    for role, patterns in _PROFILE_ORGANS:
        path = _newest(repo, patterns)
        if path is not None:
            profile_refs[role] = {"path": str(path), "excerpt": _excerpt(path)}
        else:
            profile_refs[role] = {"path": None, "excerpt": ""}

    fork_text = _fork_text(repo, fork_id) if fork_id else []
    # THE RETURN LEG (ruling_recall): ``prior_verdicts`` below is the WHOLE ledger, flat
    # and unranked — every banked row, live or retired, in one dump. That is a carrier,
    # not a retrieval: a judge reading it cannot tell which of his calls bear on THIS
    # question, and a retracted ruling sits there looking exactly like a standing one.
    # ``relevant_rulings`` is the read-back proper — the LIVE slice ranked against this
    # question as typed rows with their refs, plus the provenance that says how they were
    # chosen and what was scanned. Both channels ride: the dump stays for the callers that
    # audit the whole ledger (``fork_adjudicator._frame_complete`` checks it), the slice is
    # what a judge actually reads.
    from laplace.engine import ruling_recall
    recalled = ruling_recall.recall(
        repo, "\n".join([question] + list(fork_text)), cap=_RECALL_CAP)
    frame = {
        "question": question,
        "session_memory": __import__("laplace.engine.session_memory", fromlist=["brief"]).brief(repo),
        "fork_id": fork_id,
        "profile_refs": profile_refs,
        "ruling_corpus": harvest_ruling_corpus(repo),
        "prior_verdicts": load_verdicts(repo),
        "relevant_rulings": recalled["rows"],
        "relevant_rulings_provenance": recalled["provenance"],
        "fork_text": fork_text,
        # the THIRD input — his structural voice as evidence (dial-gated, honest)
        "form_exemplars": build_form_exemplars(
            repo, question, fork_text=fork_text, k=form_k, dials=dials),
    }
    return frame


# ------------------------------------------------------------------------- the writes
def _validate(ruling: dict) -> None:
    missing = [k for k in REQUIRED_KEYS if k not in ruling]
    if missing:
        raise ValueError(f"ruling missing required key(s): {missing}")
    if not str(ruling["id"]).startswith("PV-"):
        raise ValueError(f"ruling id must be a PV-<stamp>-<slug>: {ruling['id']!r}")
    if ruling["confidence"] not in CONFIDENCE_LEVELS:
        raise ValueError(
            f"confidence must be one of {sorted(CONFIDENCE_LEVELS)}: "
            f"{ruling['confidence']!r}")
    if not isinstance(ruling["evidence"], list):
        raise ValueError("evidence must be a list of strings")
    if not isinstance(ruling["supersedes"], list):
        raise ValueError("supersedes must be a list")


def bank_ruling(repo_root: Path | str, ruling: dict) -> dict:
    """Validate ``ruling`` against the schema and APPEND it to the verdict ledger.
    Appending is the only write; additive extra keys are allowed, the required spine
    is enforced. Returns the banked record unchanged (no ``contested`` prospective
    veto — that field stays ``null`` at bank; correction is retrospective)."""
    _validate(ruling)
    _append_jsonl(_ledger_path(repo_root), ruling)
    return ruling


def make_ruling_id(slug: str, when: _dt.datetime | None = None) -> str:
    """``PV-<UTCstamp>-<slug>`` — the id shape :func:`bank_ruling` validates."""
    ts = (when or _dt.datetime.now(_dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    clean = re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-") or "ruling"
    return f"PV-{ts}-{clean}"


def contest_ruling(repo_root: Path | str, target_id: str, reason: str,
                   by: str = "author", **extra) -> dict:
    """Retrospective correction: APPEND a ``kind:"contest"`` record referencing
    ``target_id``. The original verdict is NEVER edited — the ledger is append-only,
    and a contest is a new node the live view reconciles (this is the shape *"it's no
    good if I hold the veto"* takes: correction lands after, through the record)."""
    rec = {
        "id": make_ruling_id(f"contest-{target_id}"),
        "kind": "contest",
        "date": _dt.date.today().isoformat(),
        "contests": target_id,
        "reason": reason,
        "by": by,
    }
    rec.update(extra)
    _append_jsonl(_ledger_path(repo_root), rec)
    return rec


def confirm_ruling(repo_root: Path | str, target_id: str, reason: str = "",
                   by: str = "author", **extra) -> dict:
    """The affirmative twin of :func:`contest_ruling`: APPEND a ``kind:"confirm"`` record
    affirming ``target_id`` stands. Append-only, retrospective (never an in-place edit) —
    the same shape a contest takes, the opposite sign. A confirmed verdict leaves the
    desk's contestable set: he looked and let it stand, and that is on the record (the
    autonomy holds; the confirm is a witnessed affirmation, not a re-grant of a veto)."""
    rec = {
        "id": make_ruling_id(f"confirm-{target_id}"),
        "kind": "confirm",
        "date": _dt.date.today().isoformat(),
        "confirms": target_id,
        "reason": reason,
        "by": by,
    }
    rec.update(extra)
    _append_jsonl(_ledger_path(repo_root), rec)
    return rec


def load_verdicts(repo_root: Path | str) -> list[dict]:
    """Every banked verdict via the tolerant counted read (a poisoned line is skipped,
    never fatal). Empty list when the ledger doesn't exist yet."""
    return _read_jsonl(_ledger_path(repo_root))
