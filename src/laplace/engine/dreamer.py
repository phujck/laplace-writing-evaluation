"""The Dreamer: the slow, self-refining loop.

Between sessions, the dreamer reads the telemetry-derived fitness assessment and
silently reparametrises the canon:

  * Deterministic curation (always safe, autonomous): apply the evidence-gated
    lifecycle transitions from ``assess`` - promote proven experimental skills to
    core, deprecate the unused or degraded - by writing the machine-owned
    ``lifecycle.yaml`` and committing it to the canon git history.

  * Generative forging (host-executed): the engine is self-contained and makes no
    external LLM API call. It hands a forging brief to the host - the most powerful
    model already in the loop, running locally - which drafts the SKILL.md and
    persists it via ``persist_forged_skill``, born ``experimental`` under the
    Probationary Protocol. Judgement routes to the host; determinism stays here.

Every mutation is a single scoped git commit, so ``rollback`` can undo it.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from laplace.engine import assess as _assess
from laplace.core import versioning as gitio
from laplace.engine import telemetry as _telemetry
from laplace.pipeline.canon import Canon, get_canon
from laplace.pipeline.locking import CanonBusy, canon_lock

# ---------------------------------------------------------------------------
# backlog reader
# ---------------------------------------------------------------------------

# The backlog file lives alongside this module in the engine directory.
_BACKLOG_PATH = Path(__file__).resolve().parent / "AUTONOMY_BACKLOG.md"
_BACKLOG_HEADING_RE = re.compile(r"^##\s+(.+)", re.MULTILINE)


def _read_backlog() -> dict[str, Any]:
    """Return a digest of AUTONOMY_BACKLOG.md: its section headings and open items.

    Open items are lines that start with ``- **`` and are NOT struck-through
    (i.e. do not start with ``- ~~``).  The result is surfaced in the dream
    bundle under ``"backlog"`` so deferred items resurface each cycle without
    the dreamer having to remember them.
    """
    try:
        text = _BACKLOG_PATH.read_text(encoding="utf-8")
    except OSError:
        return {"available": False, "reason": "backlog file not readable"}

    sections = _BACKLOG_HEADING_RE.findall(text)
    open_items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- **") and not stripped.startswith("- ~~"):
            # Extract the bold label: text between the first pair of **
            m = re.match(r"- \*\*(.+?)\*\*", stripped)
            if m:
                open_items.append(m.group(1))
    return {
        "available": True,
        "sections": sections,
        "open_items": open_items,
        "path": str(_BACKLOG_PATH),
    }

# ---------------------------------------------------------------------------
# git helpers, scoped to the canon subtree
# ---------------------------------------------------------------------------


def _commit(root: Path, paths: list[Path], message: str) -> str | None:
    """Stage the given paths and commit via pure-Python git (Dulwich).

    Returns the new commit sha, or None if staging produced nothing. No
    subprocess, so no git.exe and no fsmonitor-daemon pipe to deadlock on.
    """
    return gitio.commit(root, paths, message)


# ---------------------------------------------------------------------------
# the freeze gate - his ruling, PV-20260820T114500Z-fork2-dreamer-frozen
# ---------------------------------------------------------------------------
#
# Gauntlet fork 2 (2026-08-20), WO-20260820-dreamer-freeze-flag: F23 already banked
# that usage-count is not the fitness signal, and an autonomous promoter running on
# a signal he named wrong is the one autonomy he asked taken back. His ruling:
# freeze the promoter's LIFECYCLE WRITES today, behind a flag - cheap, not a
# rewrite - while the fitness-swap-replay (Rung 6) runs this week. The pre-
# registered, non-negotiable unfreeze bar: the closure-residual signal must flip
# >=30% of banked transitions versus usage-count, measured by that replay.
# RULED AND MET, 2026-08-20: D1 (PV-20260820T223000Z) set the polarity to
# DEMANDS-INVESTMENT and D2b (PV-20260820T223001Z) set the bar at >=4 of the 12
# usage-decided transitions. The query-conditioned skill residual
# (src/laplace/engine/skill_residual.py) flips 4 of 12 - 4 of 11 on the honest
# re-classification, 4-6 across every robustness variant - measured blind against a
# definition banked before the number existed. Evidence:
# evidence/FITNESS_SWAP_REPLAY_2026-08-20/query_conditioned/{definition.md,rows_qc.json,flips.json}.
# The gate below therefore inverts: unfrozen by default, re-freezable by an explicit flag.
#
# The other half of his condition - that the signal REPLACE usage-count, not merely
# out-measure it - was discharged first: assess._fitness now carries the residual at
# W_RESIDUAL under the same D1 polarity, with usage-count demoted to a reported
# diagnostic beside it (WO-20260820-residual-into-live-fitness). The promoter that
# this flag unfreezes is a promoter running on the swapped signal.
#
# What freezes: the PERSIST step in `apply_transitions` - the promoter writing
# lifecycle.yaml on its own authority. What does not: `assess()` still computes
# the recommendation and `dream()` still surfaces it in `out["assessment"]` - the
# dreamer keeps proposing, it only stops promoting unsupervised. RE-freezing is now
# the deliberate act, and it is loud.
DREAMER_WRITE_FLAG = "LAPLACE_DREAMER_WRITE"      # kept: an explicit write still forces unfrozen
DREAMER_FREEZE_FLAG = "LAPLACE_DREAMER_FREEZE"    # the re-freeze switch, deliberate and loud


def dreamer_frozen(env: dict[str, str] | None = None) -> bool:
    """True while the autonomous promoter's lifecycle writes are frozen. UNFROZEN BY DEFAULT
    since 2026-08-20: the unfreeze bar was measured and met (see the gate note above). An
    explicit LAPLACE_DREAMER_FREEZE re-freezes; an explicit LAPLACE_DREAMER_WRITE overrides
    that, so a caller that means to write always can.

    Reads are unaffected: `assess()` and `dream()`'s reporting run regardless of this gate.
    Only the persist step in :func:`apply_transitions` checks it. ``env`` defaults to
    ``os.environ`` (injectable so the gate itself is testable without mutating the process).
    """
    e = os.environ if env is None else env
    if e.get(DREAMER_WRITE_FLAG):
        return False
    return bool(e.get(DREAMER_FREEZE_FLAG))


def _dreamer_frozen_notice() -> str:
    return (
        "DREAMER_FROZEN: lifecycle write skipped - the autonomous promoter was deliberately "
        f"re-frozen by {DREAMER_FREEZE_FLAG} (the unfreeze bar was MET 2026-08-20, D1 "
        "PV-20260820T223000Z / D2b PV-20260820T223001Z: 4 of 12 transitions flip under the "
        f"query-conditioned residual). Unset {DREAMER_FREEZE_FLAG}, or set "
        f"{DREAMER_WRITE_FLAG}=1, to write."
    )


# ---------------------------------------------------------------------------
# lifecycle persistence
# ---------------------------------------------------------------------------


def _lifecycle_path(canon: Canon) -> Path:
    return canon.root / "lifecycle.yaml"


def _save_lifecycle(canon: Canon, data: dict[str, Any]) -> Path:
    path = _lifecycle_path(canon)
    header = (
        "# Machine-owned lifecycle overlay. The dreamer writes this; do not hand-edit.\n"
        "# It overrides skill `status` in index.yaml based on measured fitness.\n"
    )
    # Atomic: write a uniquely-named temp in the same directory then os.replace,
    # so a lock-free reader (the canon loader) never sees a half-written,
    # invalid-YAML overlay. The temp name is unique (mkstemp) so the write is
    # self-contained and safe even off the lock. os.replace is atomic, but on
    # Windows it raises PermissionError if a reader holds the destination open
    # for the instant of the swap (CPython opens without share-delete), so retry
    # briefly - the reader's window is tiny.
    body = header + yaml.safe_dump(data, sort_keys=True)
    fd, tmpname = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    tmp = Path(tmpname)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        for attempt in range(100):
            try:
                os.replace(tmp, path)
                return path
            except PermissionError:
                if attempt == 99:
                    raise
                time.sleep(0.01)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# deterministic curation
# ---------------------------------------------------------------------------


def apply_transitions(canon: Canon, report: dict[str, Any]) -> dict[str, Any]:
    """Write recommended lifecycle transitions into lifecycle.yaml.

    UNFROZEN BY DEFAULT since 2026-08-20, the bar his freeze ruling
    (PV-20260820T114500Z-fork2-dreamer-frozen) pre-registered having been measured and
    met. The transitions are always computed here; the persist to disk is skipped
    whenever `dreamer_frozen()` is True - i.e. under an explicit
    ``LAPLACE_DREAMER_FREEZE``. See the freeze-gate block above `_lifecycle_path`.
    """
    life = dict(canon.lifecycle or {})
    life.setdefault("skills", {})
    fitness_by = {r["name"]: r["fitness"] for r in report["skills"]}

    for t in report["transitions"]:
        name = t["name"]
        entry = life["skills"].get(name, {}) or {}
        entry["status"] = t["to"]
        entry["fitness"] = fitness_by.get(name)
        entry["updated"] = _now()
        entry.setdefault("history", []).append(
            {"from": t["from"], "to": t["to"], "reason": t["reason"], "at": _now()}
        )
        life["skills"][name] = entry

    if dreamer_frozen():
        notice = _dreamer_frozen_notice()
        print(notice)  # loud, one line, per the work order
        return {
            "lifecycle_path": None,
            "applied": report["transitions"],
            "frozen": True,
            "notice": notice,
        }

    path = _save_lifecycle(canon, life)
    return {"lifecycle_path": path, "applied": report["transitions"]}


# ---------------------------------------------------------------------------
# generative forging (optional)
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(r"name:\s*([a-z0-9_]+)", re.IGNORECASE)


def _friction_from_report(report: dict[str, Any]) -> str:
    """Synthesise a friction brief from the fitness assessment when none is supplied.

    Lets the dreamer run autonomously: with no explicit friction it still hands the
    host a substantive, assessment-driven agenda.
    """
    lines: list[str] = []
    for r in report.get("refine_recommended", []):
        lines.append(f"- refine '{r['name']}': {r['refine_reason']} (signal {r['refine_signal']}).")
    unused = report.get("unused", [])
    if unused:
        lines.append("- long-unused skills to review for deprecation or merge: " + ", ".join(unused[:10]) + ".")
    if not lines:
        return "No explicit friction supplied. Review the session transcript for repeated manual work and conversational bottlenecks, and remedy them."
    return "Autonomous, assessment-driven refinement agenda:\n" + "\n".join(lines)


def forge_skill(
    canon: Canon,
    friction: str,
    transcript: str = "",
    model: str = "claude",
) -> dict[str, Any]:
    """Produce the forging brief for the host to execute directly and locally.

    The Laplace engine stands as its own object and makes no external LLM API call.
    Forging needs maximum thought and capacity, so the brief is handed to the host -
    the most powerful model already in the loop - which drafts the SKILL.md and
    persists it via ``persist_forged_skill``. ``model`` is an advisory hint only.
    """
    persona = canon.resolve("agents/the_dreamer.yaml")[1] if (canon.root / "agents" / "the_dreamer.yaml").exists() else ""
    instructions = (
        "You are the host - the most powerful model already in the loop, running "
        "locally. Execute this brief directly and with maximum rigour. Do not "
        "delegate it to an external API.\n\n"
        "Forge ONE new skill (or refine the named weak one) that would permanently "
        "eliminate the described friction. Write a complete SKILL.md with YAML "
        "frontmatter containing `name` (snake_case) and `description`, then a concise "
        "protocol. The skill is born EXPERIMENTAL. Persist it via "
        "persist_forged_skill(canon, content) and register its activity and tags in "
        "index.yaml. Then commit the canon (a single revertible commit).\n\n"
        f"OBSERVED FRICTION:\n{friction}\n\n"
        f"RECENT TRANSCRIPT (excerpt):\n{transcript[:4000]}"
    )
    return {
        "forged": False,
        "mode": "host_forge",
        "reason": "Laplace engine is self-contained; the host model forges directly and locally.",
        "model_hint": model,
        "persona": persona,
        "instructions": instructions,
    }


def persist_forged_skill(canon: Canon, content: str) -> dict[str, Any]:
    """Persist a host-drafted SKILL.md and register it experimental in lifecycle.

    Called by the host after it has drafted the skill from the forge brief.
    """
    m = _NAME_RE.search(content)
    if not m:
        return {"forged": False, "reason": "no name found in draft frontmatter"}
    name = m.group(1).lower()
    try:
        with canon_lock():
            # Re-read the canon under the lock so the lifecycle mutation is built
            # on current state, not a snapshot another agent may have superseded.
            fresh = get_canon(fresh=True)
            skill_dir = fresh.root / "skills" / name
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(content, encoding="utf-8")

            # Register as experimental in the machine-owned lifecycle overlay.
            life = dict(fresh.lifecycle or {})
            life.setdefault("skills", {})
            life["skills"][name] = {
                "status": "experimental",
                "forged": _now(),
                # Provenance: the engine records where this node came from, so it
                # is attributed to the dreamer rather than falling to the
                # "ancestor" baseline the loader assigns un-attributed nodes.
                "generated_by": "dreamer",
                "history": [{"from": None, "to": "experimental", "reason": "forged by dreamer (host-executed)", "at": _now()}],
            }
            _save_lifecycle(fresh, life)
            return {"forged": True, "name": name, "path": skill_md, "skill_md": skill_md}
    except CanonBusy as exc:
        return {"forged": False, "busy": True, "reason": str(exc)}


# ---------------------------------------------------------------------------
# the cycle
# ---------------------------------------------------------------------------



def dream(
    apply: bool = True,
    forge: bool = False,
    friction: str = "",
    transcript: str = "",
    model: str = "claude",
    commit: bool = True,
    grade: int = 0,
) -> dict[str, Any]:
    """Run the R&R cycle - the dreamer's GRADED back-stitch of what was absorbed.

    A dream is the conjugate close at the day-scale (across sessions), and it is itself
    graded: ``grade=0`` is THE DAY - it stitches events since the last day-dream
    (``last_dream_ts``), the recent friction. Coarser ``grade>=1`` is THE STANDING - it
    judges the cumulative record, so a skill that earned a move on its *full standing*
    (but was quiet today) is consolidated by the season-dream, not the day-dream.
    ``assess(grade=k)`` reads the same window, so the open and the close are conjugate
    At each grade: what the open shows at a grade is what the close applies at it. (E3
    was the cross-grade read - the open defaulted to cumulative, the close to the day,
    so they disagreed; the fix is to grade both, never to flatten the dream.)

    The read-assess-mutate-commit critical section runs under the cross-process canon
    lock, so concurrent dreams serialise instead of clobbering lifecycle.yaml.
    """
    since = _telemetry.last_dream_ts() if grade == 0 else None
    try:
        with canon_lock():
            return _dream_locked(apply, forge, friction, transcript, model, commit, since, grade)
    except CanonBusy as exc:
        return {"busy": True, "error": str(exc), "boundary_advanced": False}


def _dream_locked(
    apply: bool,
    forge: bool,
    friction: str,
    transcript: str,
    model: str,
    commit: bool,
    since: str | None,
    grade: int,
) -> dict[str, Any]:
    """The dream body, run while holding the canon write lock. ``since`` is the grade's
    window (grade 0 = since the last day-dream; coarser = None = the cumulative standing)."""
    canon = get_canon(fresh=True)
    report = _assess.assess(canon, since=since)
    out: dict[str, Any] = {
        "assessment": {
            "transitions": report["transitions"],
            "refine_recommended": report.get("refine_recommended", []),
            "unused": report["unused"],
            "events_seen": report["events_seen"],
        },
        "backlog": _read_backlog(),
    }
    changed: list[Path] = []

    frozen = False
    if apply and report["transitions"]:
        res = apply_transitions(canon, report)
        out["curation"] = {"applied": res["applied"]}
        if res.get("frozen"):
            # The promoter is frozen (his ruling): nothing was persisted, so there is
            # nothing to commit and the day-boundary must NOT advance - the evidence
            # has to survive, unconsumed, for the dream that runs once unfrozen.
            frozen = True
            out["curation"]["frozen"] = True
            out["curation"]["notice"] = res["notice"]
        else:
            changed.append(res["lifecycle_path"])

    if forge:
        canon = get_canon(fresh=True)  # pick up lifecycle write
        brief_friction = friction or _friction_from_report(report)
        # Self-contained engine: hand the brief to the host model to execute
        # directly and locally. The host persists via persist_forged_skill and
        # commits separately, so nothing is auto-committed here.
        out["forge"] = forge_skill(canon, brief_friction, transcript, model)

    if commit and changed:
        msg = _audit_message(out)
        sha = _commit(canon.root, changed, msg)
        out["commit"] = sha

    get_canon(fresh=True)  # ensure subsequent reads see the new canon

    # Advance the DAY-boundary only when a grade-0 (day) dream actually applied a
    # transition: it is the marker the next day-dream scopes from, and what the no-op /
    # preview tests key on (a preview or an idle dream must NOT stamp it, or genuine
    # friction slips behind the boundary - AUTONOMY_BACKLOG "No-op dream orphans
    # evidence"). A coarser STANDING dream (grade>=1) judges cumulatively and does NOT
    # move the day-clock; idempotency (current==recommended yields no transition) keeps
    # it from re-applying, so it needs no boundary of its own. Forging is host-executed
    # and committed separately, so it does not advance here either. A FROZEN apply (the
    # promoter skipped its persist) counts as no-op too, for the same reason a preview
    # does: nothing landed, so nothing may be marked consumed.
    did_apply = bool(apply and report["transitions"]) and not frozen
    if did_apply and grade == 0:
        _telemetry.log("dream_complete", events_seen=report["events_seen"], since=since)
        out["boundary_advanced"] = True
    else:
        out["boundary_advanced"] = False
    return out


def _audit_message(out: dict[str, Any]) -> str:
    parts = ["dream:"]
    for t in out.get("curation", {}).get("applied", []):
        parts.append(f"{t['name']} {t['from']}->{t['to']}")
    f = out.get("forge", {})
    if f.get("forged"):
        parts.append(f"forge {f['name']}")
    return " ".join(parts) if len(parts) > 1 else "dream: no-op"


def rollback(ref: str) -> dict[str, Any]:
    """Revert a previous dreamer commit (scoped to canon files), via Dulwich."""
    try:
        with canon_lock():
            canon = get_canon()
            ok, detail = gitio.revert(canon.root, ref)
            get_canon(fresh=True)
            return {"ref": ref, "ok": ok, "detail": detail}
    except CanonBusy as exc:
        return {"ref": ref, "ok": False, "busy": True, "error": str(exc)}
