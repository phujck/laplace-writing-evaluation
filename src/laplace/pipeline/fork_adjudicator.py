"""The fork adjudicator — the standing DRIVER that CLOSES parked forks instead of
warning about them.

His steer is this module's whole spine (PV-20260716T151557Z, GENUINELY-HIS, verbatim):
*"I do not want to see any decisions waiting for me… If it shows up on my desk and I
do not know how to decide, that is a failure… There is only one thing, so there is
almost always a correct answer that you simply wanted to avoid the work for, that is a
fail. You are the orchestrator, not the deferrer."* The fork-law (STANDING_LAW.md,
2026-07-12 amendment) already commands the loop — *a derivable fork is unfinished work
wearing a fork's clothes: derive it, decide it, bank it; his correction is retrospective
through the ledger, never prospective through a queue.* Every organ existed
(``author_proxy`` frames + banks; ``close_checklist.check_fork_adjudication`` ENUMERATES
parked forks and WARNs) — but nothing drove them. This is the driver.

**builder ≠ judge — no model call anywhere in this module.** It enumerates parked
forks, assembles the minimal-sufficient frame (:mod:`laplace.engine.author_proxy`), and emits a
dispatch MANIFEST a judge consumes (the :func:`growth_adjudicator.emit_dispatch_manifest`
idiom, hoisted-frame schema 2). On a ruling a dispatched judge returns, it VALIDATES and
BANKS via :func:`author_proxy.bank_ruling`.

**One enumeration, two consumers (the up-conjugate law).** :func:`enumerate_forks` is the
ONE fork scan — OPEN_STACK 🔴 author-forks *plus* ``corpus_friction/*.jsonl`` live
``fork`` records. :func:`enumerate_parked_forks` is the driver's door (the unreferenced
tail); ``close_checklist.check_fork_adjudication`` consumes the SAME
:func:`enumerate_forks` for its PASS/WARN split. Neither carries its own copy.

**GENUINELY-HIS routing is FAIL-CLOSED to his steer.** A route to him REQUIRES the
complete decision frame attached AND a stated ``non_derivable_reason`` — frame-or-it-
does-not-route (:func:`route_genuinely_his`, enforced again at :func:`bank_fork_ruling`).
The routed item carries everything needed to decide in seconds; a naked deferral cannot
be produced by this code.

**MODES.**
- ``dry-run`` (DEFAULT, :func:`drive`): enumerate + frames + manifest to a scratch dir;
  **ZERO ledger writes**. This is the only mode any automated path (the close hook) fires.
- ``live`` (:func:`bank_fork_ruling`, CLI ``--live``): banks judge-returned rulings. It is
  NOT the default and is invoked by NO automated path here — the first live pass is a
  supervised, in-session act, by design.

**Sibling standing consumers — documented invocation points, NOT auto-fired here** (his
"draft halves only" ruling on the standing loop):
- ``evolution_consumer.consume(manuscript_dir, corpus, net, out_dir, repo_root)``
  (``evolution_consumer.py:588``) — drafts contracts for every open intent; draft-only.
- ``evolution_consumer.apply_plan_proposals(out_dir, corpus, by=…)``
  (``evolution_consumer.py:694``, Fork-8 ruled ``PV-20260713T221204Z-weld-apply-bridge``)
  — stands up the derivable projection-intents through the storyboard door.
  Both belong in the same close/drain the fork driver's dry-run hook rides; both are left
  for a supervised wire (each mutates real state), never auto-fired from this module.
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from laplace.engine import author_proxy

_LIVE_MARKER = "\U0001f534"  # 🔴 — OPEN_STACK's live status legend
# THE fork-id shape (this module owns it; close_checklist consumes this enumeration)
_FORK_ID_RE = re.compile(r"\bF[A-Z]*Q?\d+[a-z]?\b|\bFQ\d+\b")

DEFAULT_MANIFEST_NAME = "fork_adjudication_manifest.json"

#: the manifest-level task statement — the question the ONE hoisted frame answers (the
#: per-fork keep/decide call rides each packet's own ``question``, see :func:`build_lite_packet`).
MANIFEST_QUESTION = (
    "FORK-LAW adjudication pass — each packet names one live fork parked with no proxy "
    "verdict. Per the 2026-07-12 fork-law: DERIVE and DECIDE it (rule + evidence + "
    "confidence HIGH/MEDIUM), or route GENUINELY-HIS with a non_derivable_reason and the "
    "frame attached. A parked fork with a derivable answer is a fail; a route without a "
    "frame is a fail (his steer PV-20260716T151557Z)."
)

#: callable-shape docs travelling in every manifest's ``bank`` slot — the contract a
#: dispatched judge fulfils to produce a bankable ruling. Stated here; never performed here.
BANK_CONTRACT: dict = {
    "function": "laplace.pipeline.fork_adjudicator.bank_fork_ruling",
    "signature": "bank_fork_ruling(repo_root, ruling) -> dict",
    "kind": "fork-adjudication",
    "required_keys": list(author_proxy.REQUIRED_KEYS),
    "confidence_levels": sorted(author_proxy.CONFIDENCE_LEVELS),
    "id_shape": "PV-<UTCstamp>-<slug>  (via author_proxy.make_ruling_id)",
    "route_to_him_is_fail_closed": {
        "when": "confidence == 'GENUINELY-HIS'",
        "required_extra_keys": ["non_derivable_reason", "frame"],
        "rule": (
            "a GENUINELY-HIS ruling MUST carry a non-empty non_derivable_reason AND the "
            "complete decision frame — frame-or-it-does-not-route. The banked record keeps "
            "the reason plus a bounded frame_digest (the megabyte frame is not duplicated "
            "into the ledger); the routed desk item carries the whole frame."
        ),
    },
    "note": (
        "The dispatched judge returns a ruling dict carrying the required keys; the "
        "consumer calls bank_fork_ruling(repo_root, ruling), which stamps "
        "kind='fork-adjudication' and appends via author_proxy.bank_ruling. Append-only, "
        "decide-and-bank, contested-not-veto: a correction is a later kind='contest' "
        "record, never an in-place edit."
    ),
}


# ------------------------------------------------------------------ the fork model
@dataclass(frozen=True)
class ParkedFork:
    """One live fork the driver must close. ``key`` is the handle a verdict is checked to
    reference (an F-style id, else a short title slug, else the friction record id);
    ``source`` is ``"open_stack"`` or ``"corpus_friction"``; ``fork_id`` threads into
    :func:`author_proxy.assemble_decision_frame`; ``referenced`` is True when a proxy
    verdict already names the key (a decided fork, not parked)."""
    key: str
    source: str
    summary: str
    fork_id: str
    node: str
    referenced: bool


# ------------------------------------------------------------------ the enumeration
def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _open_stack_forks(text: str) -> list[tuple[str, str, str]]:
    """OPEN_STACK's live 🔴 author-forks as ``(key, row, title)`` — the legacy
    ``| F<n> | …`` table rows AND the newer ``- **… 🔴`` bullets. Key is an F-style id
    when the row carries one, else a short slug of the bold title: the handle a verdict
    is checked to reference. This is THE derivation the close detector consumes."""
    out: list[tuple[str, str, str]] = []
    for ln in text.splitlines():
        s = ln.lstrip()
        is_table = s.startswith("| F") and ln.count("|") >= 3 and _LIVE_MARKER in ln
        is_bullet = s.startswith("- **") and _LIVE_MARKER in ln
        if not (is_table or is_bullet):
            continue
        m = _FORK_ID_RE.search(ln)
        bold = re.search(r"\*\*(.+?)\*\*", ln)
        title = bold.group(1) if bold else ln.strip()
        if m:
            key = m.group(0)
        else:
            key = " ".join(re.findall(r"[A-Za-z0-9]+", title)[:4]).upper() or ln.strip()[:40]
        out.append((key, ln.strip(), title[:120]))
    return out


def _friction_forks(repo: Path) -> list[tuple[str, str, str]]:
    """``corpus_friction/*.jsonl`` live ``fork`` records as ``(id, one-line, node)``,
    filtered through ``friction_consumer.open_frictions`` so retirement-by-supersession is
    honoured — the SAME scan the desk ``forks`` class runs (``desk._desk_forks``)."""
    from laplace.pipeline import friction_consumer
    out: list[tuple[str, str, str]] = []
    d = repo / "corpus_friction"
    if not d.is_dir():
        return out
    seen: set[str] = set()
    for led in sorted(d.glob("*.jsonl")):
        for r in friction_consumer.open_frictions(_read_jsonl(led)):
            if r.get("kind") != "fork":
                continue
            fid = str(r.get("id") or "fork")
            if fid in seen:
                continue
            seen.add(fid)
            out.append((fid, friction_consumer._one_line(r), str(r.get("node") or fid)))
    return out


def _verdict_blobs(repo: Path) -> list[str]:
    return [json.dumps(v, ensure_ascii=False) for v in author_proxy.load_verdicts(repo)]


def enumerate_forks(repo_root: Path | str) -> list[ParkedFork]:
    """the one fork scan (the up-conjugate enumeration): every live fork across both
    stores — OPEN_STACK 🔴 author-forks AND ``corpus_friction`` live ``fork`` records —
    each tagged with whether a proxy verdict already names its key. Consumed by
    :func:`enumerate_parked_forks` (the driver) AND
    ``close_checklist.check_fork_adjudication`` (the close). NEVER calls a model."""
    repo = Path(repo_root)
    blobs = _verdict_blobs(repo)
    forks: list[ParkedFork] = []

    open_stack = repo / "OPEN_STACK.md"
    if open_stack.is_file():
        text = open_stack.read_text(encoding="utf-8", errors="replace")
        for key, row, title in _open_stack_forks(text):
            forks.append(ParkedFork(
                key=key, source="open_stack", summary=row, fork_id=key, node=title,
                referenced=any(key in b for b in blobs)))

    for fid, summary, node in _friction_forks(repo):
        forks.append(ParkedFork(
            key=fid, source="corpus_friction", summary=summary, fork_id=fid, node=node,
            referenced=any(fid in b for b in blobs)))
    return forks


def enumerate_parked_forks(repo_root: Path | str) -> list[ParkedFork]:
    """The driver's door: the live forks with NO proxy verdict naming them — the parked
    set the driver frames and closes-or-routes. Exactly :func:`enumerate_forks` filtered
    to ``not referenced`` (one enumeration, two consumers)."""
    return [f for f in enumerate_forks(repo_root) if not f.referenced]


# ------------------------------------------------------------------ the frame / packets
def _question_for(fork: ParkedFork) -> str:
    """One parked fork → the task statement its packet carries. Names the source, the
    key, the fork's own text, and the two lawful outcomes (decide / route fail-closed)."""
    src = ("OPEN_STACK 🔴 author-fork" if fork.source == "open_stack"
           else "corpus_friction fork record")
    return (
        f"FORK-LAW — the {src} {fork.key!r} stands parked with no proxy verdict. DECIDE it "
        f"(rule + evidence + confidence HIGH/MEDIUM) if derivable, else route GENUINELY-HIS "
        f"with a non_derivable_reason (his person, his name in the world, or a real physics "
        f"trigger) and the frame attached. Node: {fork.node}. Fork text: {fork.summary}"
    )


def assemble_manifest_frame(repo_root: Path | str) -> dict:
    """The one frame every packet in a manifest shares — the profile organs + ruling
    corpus + prior verdicts, assembled once from :data:`MANIFEST_QUESTION` (fork-invariant).
    Hoisted to the manifest top-level so the judge reads it once; each packet carries only
    its own fork text (see :func:`build_lite_packet`). NEVER calls a model."""
    return author_proxy.assemble_decision_frame(repo_root, MANIFEST_QUESTION)


def build_lite_packet(fork: ParkedFork) -> dict:
    """One parked fork → a FRAME-LESS packet ``{fork, question, fork_text}``. The shared
    frame is hoisted to the manifest top-level (:func:`assemble_manifest_frame`);
    rebuilding it per packet is the flatten reflex — the whole ruling corpus duplicated
    once per fork. Here the packet keeps only its own task statement and rows."""
    return {
        "fork": {"key": fork.key, "source": fork.source, "node": fork.node,
                 "fork_id": fork.fork_id},
        "question": _question_for(fork),
        "fork_text": [fork.summary],
    }


def build_packet(repo_root: Path | str, fork: ParkedFork) -> dict:
    """One parked fork → a FULL-frame single packet ``{fork, frame, bank}`` (the shared
    frame plus this fork's own rows, via :func:`author_proxy.assemble_decision_frame` with
    the fork id threaded). For the single-fork path; the manifest path hoists instead.
    NEVER calls a model."""
    frame = author_proxy.assemble_decision_frame(repo_root, _question_for(fork), fork.fork_id)
    return {
        "fork": {"key": fork.key, "source": fork.source, "node": fork.node,
                 "fork_id": fork.fork_id},
        "frame": frame,
        "bank": BANK_CONTRACT,
    }


def emit_dispatch_manifest(packets: Iterable[dict], out_path: Path | str,
                           frame: dict | None = None) -> dict:
    """Write the dispatch manifest a judge/orchestrator consumes — the
    :func:`growth_adjudicator.emit_dispatch_manifest` idiom for the fork lane: a single
    self-describing JSON (``kind`` / ``count`` / ``cut_at`` / ``bank_contract`` /
    ``invocation`` + the packets). When ``frame`` is given (the shared frame from
    :func:`assemble_manifest_frame`) it is hoisted ONCE at the top level (schema 2) and
    the packets are frame-less lite packets. Returns the manifest dict; the file at
    ``out_path`` is the same content."""
    packet_list = list(packets)
    manifest = {
        "kind": "fork-adjudication",
        "count": len(packet_list),
        "cut_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "bank_contract": BANK_CONTRACT,
        "packets": packet_list,
        "invocation": None,
    }
    if frame is not None:
        manifest["schema"] = 2
        manifest["frame"] = frame
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest["invocation"] = "scripts/adjudicate_forks.py --live --rulings <judge-out>.json"
    out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    return manifest


# ------------------------------------------------------------------ fail-closed routing
def _frame_complete(frame: object) -> bool:
    """A frame counts as complete when it is a dict carrying the profile-organ channel
    with at least one resolved organ path, plus the ruling-corpus / prior-verdict channels
    (the minimal-sufficient thing a judge decides on). Bounded structural check."""
    if not isinstance(frame, dict):
        return False
    refs = frame.get("profile_refs")
    if not isinstance(refs, dict) or not any(
            isinstance(v, dict) and v.get("path") for v in refs.values()):
        return False
    return "ruling_corpus" in frame and "prior_verdicts" in frame


def _frame_digest(frame: dict) -> dict:
    """A bounded receipt that the complete frame WAS assembled — kept in the ledger in
    place of the megabyte frame (the routed desk item carries the whole thing)."""
    refs = frame.get("profile_refs") or {}
    return {
        "profile_organs": sorted(r for r, v in refs.items()
                                 if isinstance(v, dict) and v.get("path")),
        "ruling_corpus_n": len(frame.get("ruling_corpus") or []),
        "prior_verdicts_n": len(frame.get("prior_verdicts") or []),
        "fork_text_n": len(frame.get("fork_text") or []),
    }


def route_genuinely_his(repo_root: Path | str, fork: ParkedFork, ruling: dict) -> dict:
    """FAIL-CLOSED route to him — build the desk-ready routed item for a GENUINELY-HIS
    ruling. REQUIRES ``confidence == 'GENUINELY-HIS'``, a non-empty ``non_derivable_reason``,
    and the complete decision frame (re-assembled here when the ruling did not carry one) —
    frame-or-it-does-not-route. Returns the routed item carrying the WHOLE frame plus the
    reason; raises ``ValueError`` on any missing piece (a naked deferral cannot be built)."""
    if ruling.get("confidence") != "GENUINELY-HIS":
        raise ValueError("route_genuinely_his is only for GENUINELY-HIS rulings")
    reason = str(ruling.get("non_derivable_reason") or "").strip()
    if not reason:
        raise ValueError(
            "GENUINELY-HIS route REQUIRES a non_derivable_reason (why the call is his and "
            "not derivable) — frame-or-it-does-not-route (his steer PV-20260716T151557Z)")
    frame = ruling.get("frame")
    if not _frame_complete(frame):
        frame = author_proxy.assemble_decision_frame(
            repo_root, _question_for(fork), fork.fork_id)
    if not _frame_complete(frame):
        raise ValueError(
            "GENUINELY-HIS route REQUIRES the complete decision frame attached — "
            "frame-or-it-does-not-route")
    return {
        "kind": "route-genuinely-his",
        "fork": {"key": fork.key, "source": fork.source, "node": fork.node},
        "question": _question_for(fork),
        "non_derivable_reason": reason,
        "frame": frame,
    }


# ------------------------------------------------------------------ the only write
def bank_fork_ruling(repo_root: Path | str, ruling: dict) -> dict:
    """Bank a fork ruling — the ONLY ledger write (append-only, via
    :func:`author_proxy.bank_ruling`, which validates the required spine). Stamps
    ``kind:"fork-adjudication"``. GENUINELY-HIS is FAIL-CLOSED: the ruling MUST carry a
    non-empty ``non_derivable_reason`` and the complete ``frame`` — a route missing either
    is REJECTED before any write (frame-or-it-does-not-route). The heavy frame is reduced
    to a bounded ``frame_digest`` in the ledger; the routed desk item keeps the whole frame."""
    rec = dict(ruling)
    rec.setdefault("kind", "fork-adjudication")
    if rec.get("confidence") == "GENUINELY-HIS":
        if not str(rec.get("non_derivable_reason") or "").strip():
            raise ValueError(
                "GENUINELY-HIS ruling REQUIRES a non_derivable_reason — "
                "frame-or-it-does-not-route (his steer PV-20260716T151557Z)")
        if not _frame_complete(rec.get("frame")):
            raise ValueError(
                "GENUINELY-HIS ruling REQUIRES the complete decision frame attached — "
                "frame-or-it-does-not-route")
    if isinstance(rec.get("frame"), dict):
        rec["frame_digest"] = _frame_digest(rec.pop("frame"))
    return author_proxy.bank_ruling(repo_root, rec)


# ------------------------------------------------------------------ the standing pass
def drive(repo_root: Path | str, mode: str = "dry-run",
          scratch_dir: Path | str | None = None) -> dict:
    """The standing driver pass. Enumerate parked forks → hoist the shared frame → one
    lite packet per fork → a dispatch manifest a judge consumes. ``mode`` MUST be
    ``"dry-run"`` here: this function writes the manifest to a scratch dir and touches the
    ledger for NOTHING. Banking is the ``--live`` CLI path (:func:`bank_fork_ruling`),
    supervised and in-session; no automated caller of ``drive`` may bank. Returns
    ``{mode, parked, manifest_path, forks}`` — a summary a report renders."""
    if mode != "dry-run":
        raise ValueError(
            f"drive() runs dry-run only (mode={mode!r}); banking is the supervised "
            "--live CLI path, never an automated call")
    repo = Path(repo_root)
    parked = enumerate_parked_forks(repo)
    scratch = Path(scratch_dir) if scratch_dir else Path(tempfile.mkdtemp(prefix="fork-adjud-"))
    scratch.mkdir(parents=True, exist_ok=True)
    manifest_path = scratch / DEFAULT_MANIFEST_NAME
    if parked:
        frame = assemble_manifest_frame(repo)
        packets = [build_lite_packet(f) for f in parked]
        emit_dispatch_manifest(packets, manifest_path, frame=frame)
    else:
        emit_dispatch_manifest([], manifest_path)
    return {
        "mode": "dry-run",
        "parked": len(parked),
        "manifest_path": str(manifest_path),
        "forks": [{"key": f.key, "source": f.source, "node": f.node} for f in parked],
    }
