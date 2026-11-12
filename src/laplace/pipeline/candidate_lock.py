"""Candidate-lock eligibility + the round transaction + the incumbent (Phase F).

The transactional spine of the convergence loop (his hardening review, 2026-07-09):

  * a round is COMPLETE only when every expected verdict came back well-formed —
    a missing / failed / malformed verdict makes the round INCOMPLETE (the
    silence->0.5 law generalised: silence never reads as a pass, and an
    incomplete round cannot lock);
  * candidate-lock is eligible only when the HARD dims pass AND the compile is
    clean (0 undefined / 0 errors) AND the round is complete;
  * each accepted state is snapshot as an IMMUTABLE incumbent — the ``.tex``
    fragments + ``main.pdf`` + the log, copied under ``rounds/incumbent_r<N>/``,
    restorable with no reliance on the session's git state;
  * a challenger replaces the incumbent only by the dominance decision
    (``convergence.accept_candidate``, wrapped — never reimplemented); on reject
    the snapshot is RESTORED, so the challenger never silently replaces the
    incumbent.

This module OWNS none of the acceptance algebra: it wraps
``convergence.accept_candidate`` (the general incumbent/challenger dominance
decision — hard-gate precedence, incumbent seeding, voice burden-of-proof). It
adds only the round-completeness gate, the compile gate, and the snapshot/restore
transaction around that decision.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from laplace.pipeline import convergence

#: files copied into an incumbent snapshot besides every ``*.tex`` fragment.
_SNAPSHOT_EXTRAS = ("main.pdf", "main.log")
#: compile-report keys whose non-zero value means the compile is NOT clean.
#: overfull boxes are deliberately EXCLUDED (a soft floor, not a hard error).
_COMPILE_ERROR_KEYS = ("errors", "undefined", "undefined_refs", "undefined_cites",
                       "undefined_citations", "undefined_references", "fatal")


# ---------------------------------------------------------------------------
# round completeness — silence never reads as pass
# ---------------------------------------------------------------------------

def _valid_verdict(p: Any) -> bool:
    """A well-formed verdict: a dict with a label, not marked ``failed``, and a
    boolean ``clean`` (a rendered verdict). Anything else is missing/malformed."""
    return (isinstance(p, dict) and bool(p.get("label"))
            and p.get("failed") is not True and isinstance(p.get("clean"), bool))


def round_status(panel: list[dict], *, expected: Optional[list[str]] = None) -> dict:
    """Whether a round is complete. Returns ``{complete: bool, missing: [labels]}``.

    Every panel entry must be a well-formed verdict; a failed/malformed entry puts
    its label (or ``"<malformed>"``) in ``missing``. When ``expected`` is given
    (the candidate-lock roster, e.g. ``dials.lock_readers`` + the mechanical
    labels), any expected label with no valid verdict is also ``missing``. An
    empty panel with no expectation is incomplete (nothing came back)."""
    missing: list[str] = []
    valid_labels: set[str] = set()
    for p in panel or []:
        if _valid_verdict(p):
            valid_labels.add(p["label"])
        else:
            label = p.get("label") if isinstance(p, dict) else None
            missing.append(str(label) if label else "<malformed>")

    for label in (expected or []):
        if label not in valid_labels:
            missing.append(label)

    # dedupe, preserve order
    seen: set[str] = set()
    missing = [m for m in missing if not (m in seen or seen.add(m))]

    complete = not missing and (bool(valid_labels) or bool(expected))
    return {"complete": complete, "missing": missing}


# ---------------------------------------------------------------------------
# lock eligibility
# ---------------------------------------------------------------------------

def _hard_pass(round_eval: dict) -> bool:
    """Hard-dim pass from an ``evaluate_round`` result, a raw contract eval, or a
    ``{"hard": {...}}`` shape — tolerant of what the caller has to hand."""
    if not isinstance(round_eval, dict):
        return False
    if "hard_failing" in round_eval:
        return not round_eval["hard_failing"]
    if "contract" in round_eval:
        return convergence.hard_pass(round_eval["contract"])
    if "hard" in round_eval:
        return convergence.hard_pass(round_eval)
    return False


def _compile_clean(report: dict) -> tuple[bool, list[str]]:
    """Whether the compile is clean (0 undefined / 0 errors; overfull excluded).
    A falsy/absent report is NOT clean (no compile evidence never passes)."""
    if not report:
        return False, ["no compile report (silence never reads as clean)"]
    if report.get("ok") is False:
        return False, ["compile reported ok=False"]
    reasons: list[str] = []
    for k in _COMPILE_ERROR_KEYS:
        try:
            n = int(report.get(k, 0) or 0)
        except (TypeError, ValueError):
            continue
        if n > 0:
            reasons.append(f"compile has {n} {k}")
    return (not reasons), reasons


def lock_eligible(round_eval: dict, compile_report: dict,
                  round_complete: bool) -> tuple[bool, list[str]]:
    """Candidate-lock eligibility: hard dims pass AND compile clean AND round
    complete. Returns ``(eligible, reasons)`` where ``reasons`` names every gate
    that fails (empty when eligible)."""
    reasons: list[str] = []
    if not _hard_pass(round_eval):
        reasons.append("a hard dimension fails (non-compensable)")
    clean, compile_reasons = _compile_clean(compile_report)
    if not clean:
        reasons.extend(compile_reasons)
    if not round_complete:
        reasons.append("round incomplete (a verdict is missing/failed/malformed)")
    return (not reasons), reasons


# ---------------------------------------------------------------------------
# incumbent snapshot / restore — self-contained, no git reliance
# ---------------------------------------------------------------------------

def _rounds_dir(manuscript_dir: str | Path) -> Path:
    return Path(manuscript_dir) / "rounds"


def _snapshot_files(manuscript_dir: Path) -> list[tuple[Path, str]]:
    """Every file to snapshot, paired with its path RELATIVE to the manuscript
    dir (so the tree structure is restored): all ``*.tex`` fragments recursively
    (the ``rounds/`` snapshot store itself excluded), plus main.pdf / main.log."""
    out: list[tuple[Path, str]] = []
    rounds = _rounds_dir(manuscript_dir).resolve()
    for f in sorted(manuscript_dir.rglob("*.tex")):
        if rounds in f.resolve().parents:
            continue
        out.append((f, f.relative_to(manuscript_dir).as_posix()))
    for name in _SNAPSHOT_EXTRAS:
        f = manuscript_dir / name
        if f.is_file():
            out.append((f, name))
    return out


#: source suffixes the artefact fingerprint covers. Build outputs (.pdf/.log/
#: .aux/.bbl/...) are excluded on purpose: latexmk rewrites them on every compile,
#: so including them would change the fingerprint when nothing an author touched did.
_FINGERPRINT_SUFFIXES = (".tex", ".bib", ".sty", ".cls")


def tex_fingerprint(manuscript_dir: str | Path) -> str:
    """A 16-hex digest of the manuscript's SOURCE tree — the artefact's content
    identity, stable across recompiles and changed by any source edit.

    Same file-set rule as ``_snapshot_files``: recursive, with the ``rounds/``
    snapshot store excluded (its copies are not the artefact). The digest is over
    each file's relative path plus the sha256 of its bytes, in sorted path order,
    so it depends on content and layout and on nothing else — two trees with the
    same sources fingerprint identically on any machine.

    The convergence loop interpolates this into every round agent's prompt: the
    workflow harness keys its agent cache by prompt content, so a resumed run
    replays a round verbatim when the prompt is byte-identical. Carrying the
    fingerprint makes an edited tree produce different round prompts, which is
    what stops a resume from replaying a pre-edit verdict as live
    (IDEMPOTENCE_LEDGER row 14). Returns the empty string if the directory does
    not exist — the caller decides what an unfingerprintable tree means.
    """
    md = Path(manuscript_dir)
    if not md.is_dir():
        return ""
    rounds = _rounds_dir(md).resolve()
    files: list[Path] = []
    for suffix in _FINGERPRINT_SUFFIXES:
        for f in md.rglob("*" + suffix):
            if f.is_file() and rounds not in f.resolve().parents:
                files.append(f)
    lines = []
    for f in sorted(set(files)):
        lines.append(f.relative_to(md).as_posix() + " "
                     + hashlib.sha256(f.read_bytes()).hexdigest())
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]


def snapshot_incumbent(manuscript_dir: str | Path, round_n: int) -> str:
    """Copy the current manuscript state into ``rounds/incumbent_r<N>/`` and return
    the snapshot ref (the snapshot dir path). Self-contained and restorable — no
    reliance on the session's git state. A manifest records the copied files."""
    md = Path(manuscript_dir)
    dest = _rounds_dir(md) / f"incumbent_r{int(round_n)}"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"round": int(round_n),
                                "ts": time.strftime("%Y-%m-%d_%H%M%S"),
                                "files": []}
    for src, rel in _snapshot_files(md):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        manifest["files"].append(rel)
    (dest / "SNAPSHOT.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(dest)


def _resolve_ref(manuscript_dir: str | Path, ref: str | int) -> Path:
    """Resolve a snapshot ref (a dir path, a round int, or ``"r<N>"``/
    ``"incumbent_r<N>"``) to the snapshot directory."""
    md = Path(manuscript_dir)
    if isinstance(ref, int):
        return _rounds_dir(md) / f"incumbent_r{ref}"
    p = Path(ref)
    if p.is_absolute() or p.exists():
        return p
    s = str(ref)
    if s.startswith("incumbent_"):
        return _rounds_dir(md) / s
    if s.startswith("r") and s[1:].isdigit():
        return _rounds_dir(md) / f"incumbent_{s}"
    return _rounds_dir(md) / s


def restore_incumbent(manuscript_dir: str | Path, ref: str | int) -> dict:
    """Restore a snapshot's files back into the manuscript dir (overwriting the
    challenger's bytes). Returns ``{restored: [rel paths], ref: str}``. Raises
    ``FileNotFoundError`` if the snapshot or its manifest is missing."""
    md = Path(manuscript_dir)
    snap = _resolve_ref(md, ref)
    manifest_path = snap / "SNAPSHOT.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no incumbent snapshot at {snap}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored: list[str] = []
    for rel in manifest.get("files", []):
        src = snap / rel
        if not src.is_file():
            continue
        target = md / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        restored.append(rel)
    return {"restored": restored, "ref": str(snap)}


def latest_incumbent(manuscript_dir: str | Path) -> Optional[str]:
    """The highest-round incumbent snapshot dir, or ``None`` if there is none."""
    rounds = _rounds_dir(manuscript_dir)
    if not rounds.is_dir():
        return None
    best_n, best = -1, None
    for d in rounds.iterdir():
        if d.is_dir() and d.name.startswith("incumbent_r") and (d / "SNAPSHOT.json").is_file():
            try:
                n = int(d.name[len("incumbent_r"):])
            except ValueError:
                continue
            if n > best_n:
                best_n, best = n, str(d)
    return best


# ---------------------------------------------------------------------------
# the accept-or-restore transaction — wraps convergence.accept_candidate
# ---------------------------------------------------------------------------

#: sentinel telling ``record_lock`` the readability tier was not wired on this call
#: (distinct from ``readability=None``, which wires the tier with no reader reachable and
#: so blocks). A caller that predates the tier passes nothing and behaves as before.
_UNSET: Any = object()


def _run_readability_gate(manuscript_dir: str | Path,
                          dispatch: Optional[Any]) -> dict:
    """Run the whole-object readability gate against the artefact being locked, through
    the injected reader boundary (``dispatch``). Wraps ``readability_gate.grade`` so the
    lock tier stays a thin call; a test overrides this via ``record_lock``'s
    ``readability_gate`` hook."""
    from laplace.pipeline import readability_gate
    return readability_gate.grade(manuscript_dir, dispatch=dispatch)


def record_lock(manuscript_dir: str | Path, round_eval: dict, compile_report: dict,
                round_complete: bool, *, by: str | None = None,
                readability: Any = _UNSET,
                readability_gate: Any = None) -> dict:
    """Drive the release machine when a round is lock-eligible — the one invoker
    (E4b / ACT 4). The board renders FROM ``release.STATES``, but nothing ever drove
    the machine: falqon reads ``NEVER_RUN`` under a minted r2 because the converge
    loop banked rounds without ever transitioning. This is the lock organ's
    stage-completion call: a candidate that locks IS at ``CANDIDATE_LOCKED``, so when
    :func:`lock_eligible` holds the machine advances there (through
    ``UNDER_CONVERGENCE`` first, via ``ensure_at_least`` — the converge stage the loop
    was really in), consuming the SAME ``round_eval`` / ``compile_report`` /
    ``round_complete`` the lock gate already checked (``release.transition`` re-checks
    them at its own door — the invariant is enforced once, in the machine).

    **The readability tier (his readability gate).** When ``readability`` is wired (the
    orchestrator's hold-out reader boundary, or ``None`` to wire the tier with no reader
    reachable), a whole-object stranger read runs against the artefact after the local
    gates pass. A ``FAIL`` (a stranger cannot read it) or an ``UNAVAILABLE`` (the read
    could not be made — no reader, or no readable object) BLOCKS the lock regardless of
    the local greens, with the reader's mechanisms named in ``reasons``. This is the
    paper-grade twin of the whole-walk seal: local closure counts for nothing here. The
    tier is off only when ``readability`` is left unwired (``_UNSET``), so a caller that
    predates it is byte-identical to before; the converge orchestrator must wire the
    reader boundary at real lock time (fail closed once wired, never open).

    Idempotent and plain: off the eligible path it transitions NOTHING (returns
    ``{eligible: False, reasons}``); on the eligible path it is monotone — a machine
    already at or past ``CANDIDATE_LOCKED`` is a no-op forward (``ensure_at_least``),
    the lock transition itself only fires when the machine is behind it. Returns
    ``{eligible, reasons, advanced, state}`` (plus ``readability`` when the tier ran).
    Raises nothing the caller must catch on the eligible path beyond what
    ``release.transition`` already raises for a genuinely illegal advance (a stale
    bundle, a backward slide)."""
    eligible, reasons = lock_eligible(round_eval, compile_report, round_complete)
    if not eligible:
        return {"eligible": False, "reasons": reasons, "advanced": False,
                "state": None}

    # THE READABILITY TIER — a whole-object stranger read blocks the lock on a FAIL or an
    # UNAVAILABLE, regardless of the local greens. Engaged only when wired.
    if readability is not _UNSET:
        from laplace.pipeline import readability_gate as _rg
        gate = readability_gate or _run_readability_gate
        verdict = gate(manuscript_dir, readability)
        if _rg.blocks_lock(verdict):
            return {"eligible": False, "reasons": _rg.refusal_reasons(verdict),
                    "advanced": False, "state": None, "readability": verdict}

    from laplace.pipeline import release
    md = Path(manuscript_dir)
    # the converge stage the loop was really in — assert it before the lock (monotone,
    # a no-op when the machine is already there or ahead).
    release.ensure_at_least(md, "UNDER_CONVERGENCE")
    cur = release.current_state(md)
    if release._order_index(cur) >= release._order_index("CANDIDATE_LOCKED"):
        return {"eligible": True, "reasons": [], "advanced": False, "state": cur}
    side = release.transition(md, "CANDIDATE_LOCKED", by=by, evidence={
        "round_eval": round_eval, "compile_report": compile_report,
        "round_complete": round_complete})
    return {"eligible": True, "reasons": [], "advanced": True,
            "state": side.get("state", "CANDIDATE_LOCKED")}


def accept_or_restore(manuscript_dir: str | Path, ref: str | int,
                      candidate_ev: dict, incumbent_ev: dict | None, *,
                      is_voice: bool = False, neutral: dict | None = None,
                      prohibitions: dict | None = None) -> dict:
    """Decide the challenger against the incumbent and, on reject, RESTORE the
    snapshot ``ref`` (the incumbent's bytes) — the challenger never silently
    replaces the incumbent.

    Wraps ``convergence.accept_candidate`` (the dominance decision: hard-gate
    precedence, incumbent seeding, voice burden-of-proof). Returns
    ``{"accepted": bool, "reason": str, "restored": bool}``. On accept the
    challenger's bytes stay in place (the caller snapshots the new incumbent)."""
    decision = convergence.accept_candidate(
        candidate_ev, incumbent_ev, is_voice=is_voice,
        neutral=neutral, prohibitions=prohibitions)
    if decision.get("accept"):
        return {"accepted": True, "reason": decision.get("reason", ""),
                "restored": False}
    restore_incumbent(manuscript_dir, ref)
    return {"accepted": False, "reason": decision.get("reason", ""),
            "restored": True}
