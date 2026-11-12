"""close_beats.py — the GRADED close: which beats a sew-up must actually walk.

Part C accreted beats and never retired them — the same disease the wake had, and
his standing correction at the W5 close: "diary + handoff + re-embed + commit are
the grade-0 trace, always; every other beat fires ONLY if its source moved —
derived from the diff, not ritualized." This module is that derivation, and only
that: it reads what changed since the last banked close and returns, per beat,
whether it must fire and why. It NEVER runs a beat, writes anything, or gates an
exit code — it is a planner the close reads, the conjugate of tests_at_grade's
"run the shard for what moved" applied to the ritual instead of the suite.

THE MARK is contract/close_receipt.json: a successful publication with checkpoint and artifact
hashes. A commit subject or a dated handoff addition alone does not establish publication.
Without a receipt, the historical optional planner has no boundary and reports that limitation.
This planner never decides whether the default checkpoint → publication close may proceed.

THE BEAT → SOURCE MAP (from EIGEN_PROTOCOL.md Part C, grounded in what each
instrument actually reads — see the glob constants below):
  - diary / handoff / session_handoff / commit — the grade-0 trace, ALWAYS.
  - re-embed — grade-0, ALWAYS; its wire-drain sub-step only when the
    .wire_proposals.jsonl frontier is non-empty (nothing to drain otherwise).
  - rehearsal (wake re-fire + cold coverage) — grade-0, ALWAYS.
  - open_stack_sweep — grade-0, ALWAYS.
  - standing_law amend / sawbones per-skill log — SESSION FACTS, not diffable
    (only the author knows if the law moved, only the loop knows which skills
    ran); they fire=True with a plain "not diff-derivable" why, never silently
    skipped by a diff that structurally cannot see them.
  - architecture map — iff the machine moved (engine source / scripts / workflows).
  - recurrence / durable_refs / seam_liveness — iff the ledgers / durable md
    surfaces / seam artifacts those checks read actually moved.
  - effect_meter — iff the wire ledgers moved; but both are GITIGNORED (a diff
    never sees them), so this one falls back to an mtime-vs-mark heuristic, named
    as such in its why rather than pretending to be diff-derived.
  - holdout intake — iff anything under holdout/ moved.
  - suite — NEVER the flat suite: always the scoped invocation
    (``python3 -m laplace.engine.tests_at_grade --run``); on a clean tree at the mark the
    scoped shard is empty and it inherits the banked-green verdict.
"""
from __future__ import annotations

import json
import hashlib
import subprocess
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional

# ---- the source map: each gated beat's globs, grounded in what its check reads ----

# architecture map — the map moves when the MACHINE moves: engine source, the
# scripts that drive it, or the workflow wiring (Part C: "updated if a piece
# actually moved").
_ARCH_GLOBS = ("src/laplace/**", "scripts/**", ".claude/workflows/**")

# recurrence — detect_recurrence.py reads "every corpus_friction/*.jsonl ledger"
# (its docstring); the friction ledgers are its whole input surface.
_RECURRENCE_GLOBS = ("corpus_friction/*.jsonl",)

# durable_refs — check_durable_refs.py scans the DURABLE surfaces (its docstring):
# OPEN_STACK.md, HANDOFF.md, the newest SESSION_HANDOFF_*.md, EIGEN_PROTOCOL.md,
# and corpus_friction/*.jsonl. If none of those moved, no new ref can have leaked.
_DURABLE_GLOBS = (
    "OPEN_STACK.md",
    "HANDOFF.md",
    "SESSION_HANDOFF_*.md",
    "EIGEN_PROTOCOL.md",
    "corpus_friction/*.jsonl",
)

# seam_liveness — audit_silent_failures.py reads the pipeline SEAM artifacts (its
# CHECKS block): per-project economics.json beside mech_r*.json rounds,
# release/state.json, the newest conformance_*.json, and the friction ledgers.
_SEAM_GLOBS = (
    "**/economics.json",
    "**/mech_r*.json",
    "release/**",
    "**/release/**",
    "**/conformance_*.json",
    "conformance_*.json",
    "corpus_friction/*.jsonl",
)

# effect_meter — audit_effect_meter.py reads ONLY these two wire ledgers, and BOTH
# are gitignored (its docstring), so a diff structurally cannot see them; the
# heuristic below reads their mtime against the mark instead.
_WIRE_LEDGERS = (".wire_proposals.jsonl", ".wire_verdicts.jsonl")

# holdout intake — the held-out prediction machinery lives wholly under holdout/.
_HOLDOUT_GLOBS = ("holdout/**",)

# banked-what-travels (W6.2) — the produced-in-container artifacts a REMOTE close must commit
# so the author's next local pull arrives warm: round records + sidecars under any
# <manuscript>/rounds/ tree (the tray offered r1-only because later rounds never travelled,
# RW-20260713-220546-834144), and any instrumented node-region map (main.nodemap.json). These
# are already tracked-eligible (round records are NOT gitignored — verified by `git status
# --ignored` finding no round/harnessed/adjudicate artifact ignored; W6.2 banked-what-travels 2026-07-14);
# the gap was that a remote close produced them and never staged them. This beat LISTS the
# git-add-able ones; the orchestrator (which owns the seam) does the git add + commit.
_TRAVEL_GLOBS = ("**/rounds/**", "**/*.nodemap.json")

_SCOPED_SUITE = "python3 -m laplace.engine.tests_at_grade --run"


# ------------------------------------------------------------------ the mark
def _git_subprocess(root: Path, *args: str, timeout: float = 30.0):
    """One optional-planner git read, or None when unavailable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception:  # noqa: BLE001 - spawn/timeout problem is "can't tell"
        return None
    if out.returncode != 0:
        return None
    return out.stdout


def read_close_receipt(repo) -> dict | None:
    """Read the explicit publication boundary; prose and commit subjects are not receipts.

    Artifact hashes describe the accepted generation at close time. Current source may have
    changed since then, so freshness is checked by the publisher/reader, not inferred here.
    Independent successor consumption is a separate observation.
    """
    try:
        with (Path(repo) / "contract/close_receipt.json").open("rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            return None
        receipt = json.loads(raw)
        if not isinstance(receipt, dict):
            return None
        publication = receipt.get("publication")
        if (receipt.get("schema_version") != "laplace.close/1"
                or receipt.get("status") != "PUBLISHED"
                or not isinstance(receipt.get("checkpoint"), dict)
                or not receipt["checkpoint"]
                or not isinstance(publication, dict)
                or publication.get("schema_version") != "laplace.publication/1"
                or publication.get("published") is not True
                or not isinstance(publication.get("artifacts"), dict)
                or not publication["artifacts"]
                or _mark_epoch(receipt.get("closed_at")) is None):
            return None
        return receipt
    except (OSError, ValueError, TypeError):
        return None


def last_banked_close(repo) -> Optional[str]:
    """Timestamp of the latest successfully published close, or no established boundary."""
    receipt = read_close_receipt(repo)
    return receipt["closed_at"] if receipt else None


def _recovery_observation(root: Path, receipt: dict | None) -> dict:
    result = {"status": "UNVERIFIED", "source": "contract/close_recovery.json"}
    if not receipt:
        return result
    try:
        raw = (root / result["source"]).read_bytes()
        if len(raw) > 12000:
            raise ValueError("recovery record exceeds budget")
        row = json.loads(raw)
        if row.get("close_act_id") != receipt.get("act_id"):
            return {**result, "status": "OLDER-CLOSE"}
        report = (root / row["report"]).resolve()
        if not report.is_relative_to(root.resolve()) or report.stat().st_size > 24000:
            raise ValueError("invalid recovery report")
        data = report.read_bytes()
        if "sha256:" + hashlib.sha256(data).hexdigest() != row["report_sha256"]:
            raise ValueError("recovery report changed")
        if not row.get("reader_context") or row["reader_context"] == row.get("writer_context"):
            raise ValueError("independent reader context absent")
        accepted = row.get("verdict") == "accept" and json.loads(data).get("decision") == "accept"
        return {**result, "status": "RECORDED-INDEPENDENT-RECOVERY" if accepted else "RECORDED-INCOMPLETE",
                "reader_context": row["reader_context"], "report": row["report"],
                "report_sha256": row["report_sha256"], "close_act_id": row["close_act_id"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {**result, "reason": str(exc)}


def close_projection(repo, *, verify_artifacts: bool = False) -> dict:
    """A bounded, read-only view of recorded publication and the newest observed close.

    Explicit health may hash the publication artifacts. Ordinary entry reads only
    bounded receipts. Independent recovery is tied to the exact close and reader report.
    An incomplete or malformed tail is uncertainty, never an inherited PASS.
    """
    root = Path(repo)
    receipt = read_close_receipt(root)
    publication = {"status": "RECORDED" if receipt else "UNKNOWN",
                   "source": "contract/close_receipt.json",
                   "semantic_freshness": "UNVERIFIED", "successor_consumption": "UNVERIFIED"}
    if receipt:
        publication.update(at=str(receipt["closed_at"])[:40],
                           act_id=str(receipt.get("act_id") or "")[:96])
        # work.source_kernel's states for the selected Source inputs this close published.
        counts = receipt["publication"].get("source_currentness")
        if isinstance(counts, dict) and all(type(counts.get(k)) is int for k in ("current", "carried", "stale", "unknown")):
            publication["source_inputs"] = (
                f"Source inputs: {counts['current']} current, {counts['carried']} carried (pinned bytes moved or the declaration moved to another module, meaning unchanged), "
                f"{counts['stale']} stale and {counts['unknown']} unknown (published as labelled retained history)")
    else:
        publication["reason"] = "receipt missing, malformed or outside read budget"
    recovery = _recovery_observation(root, receipt)
    publication["successor_consumption"] = recovery["status"]
    if verify_artifacts and receipt:
        changed = []
        for name, expected in {**receipt["publication"]["artifacts"], **receipt["checkpoint"]}.items():
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                changed.append(name)
                continue
            with path.open("rb") as stream:
                actual = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != expected:
                changed.append(name)
        changed.extend(name for name in receipt["publication"].get("absent_artifacts", []) if (root / name).exists())
        publication.update(semantic_freshness="CHANGED" if changed else "CURRENT", changed_artifacts=changed,
                           freshness_scope="exact published artifact and checkpoint bytes")
    attempt = {"status": "UNKNOWN", "source": "contract/journal.jsonl"}
    result = {"publication": publication, "recovery": recovery, "latest_attempt": attempt,
              "journal_tail": {"bytes": 0, "truncated": False}}
    try:
        with (root / "contract/journal.jsonl").open("rb") as stream:
            size = stream.seek(0, 2)
            start = max(0, size - 65536)
            stream.seek(start)
            raw = stream.read(65536)
        result["journal_tail"] = {"bytes": len(raw), "truncated": bool(start)}
        if start:
            raw = raw.partition(b"\n")[2]  # first record may begin outside the window
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError("non-object journal record")
    except (OSError, ValueError, UnicodeError):
        attempt["reason"] = "journal missing, unreadable or malformed within bounded tail"
        return result
    starts = [row for row in rows if row.get("record") == "act"
              and row.get("act") == "sewup-close"]
    if not starts:
        attempt["reason"] = "no close attempt start in bounded journal tail"
        return result
    latest = starts[-1]
    act_id = latest.get("act_id")
    if not isinstance(act_id, str) or not act_id:
        attempt["reason"] = "latest close attempt has no valid identity"
        return result
    attempt.update(act_id=act_id[:96], at=str(latest.get("ts") or "")[:40])
    ends = [row for row in rows if row.get("record") == "act_end"
            and row.get("act_id") == act_id]
    if not ends:
        attempt["reason"] = "no terminal outcome for latest observed close"
        return result
    terminal = ends[-1]
    status = terminal.get("status")
    if status not in {"pass", "fail", "killed"}:
        attempt["reason"] = "unrecognized terminal outcome"
        return result
    attempt.update(status=status.upper(), at=str(terminal.get("ts") or "")[:40])
    summary = terminal.get("summary", "")
    if isinstance(summary, str) and summary.startswith("close_status="):
        attempt["close_status"] = summary.partition(";")[0].split("=", 1)[1][:40]
    return result


def _mark_epoch(mark: Optional[str]) -> Optional[float]:
    if not mark:
        return None
    try:
        dt = datetime.fromisoformat(mark)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


# ------------------------------------------------------------- what moved since
def _changed_since(repo, mark: Optional[str]) -> set[str]:
    """Committed paths that moved strictly AFTER the mark. dulwich's ``since`` is
    inclusive of the boundary commit (verified), and the mark IS the close, so we
    nudge the cutoff one second past it before asking gitio — we want what came
    after the close, not the close's own trace files."""
    if mark is None:
        return set()
    cutoff = mark
    try:
        cutoff = (datetime.fromisoformat(mark) + timedelta(seconds=1)).isoformat()
    except ValueError:
        pass
    from laplace.core import versioning as gitio

    paths = gitio.log_paths_since(repo, cutoff)
    return set(paths) if paths else set()


def _dirty_paths(repo) -> Optional[set[str]]:
    """The current dirty tree — staged, unstaged, untracked (porcelain). Mirrors
    tests_at_grade's own read so the two organs see the same working tree.

    None when git did not answer (failed spawn, timeout, or non-zero rc). An unread
    tree is not an empty one: returning set() for both made a dead git CLI plan the
    close as if nothing had moved, which is the fail-silent this gate exists to
    refuse. The caller reads None the way it reads an unresolvable mark — fail-heavy."""
    try:
        # -uall so a brand-new untracked MODULE is seen by its own path, not
        # collapsed to its parent dir (the close gate must never fail-silent).
        out = subprocess.run(
            ["git", "status", "--porcelain", "-z", "--untracked-files=all"], cwd=str(repo),
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    paths: set[str] = set()
    for rec in out.stdout.split("\0"):
        if len(rec) > 3:
            path = rec[3:]
            if " -> " in path:  # rename: take the new path
                path = path.split(" -> ", 1)[1]
            paths.add(path.replace("\\", "/"))
    return paths


def _moved(changed: set[str], globs: tuple[str, ...]) -> list[str]:
    """The subset of ``changed`` matching any glob (fnmatch, where ``*`` crosses
    ``/`` — so ``a/b/**`` and ``a/b/*`` both read as "anything under a/b")."""
    hit = {p for p in changed for g in globs if fnmatch(p, g)}
    return sorted(hit)


def banked_what_travels(repo) -> list[str]:
    """The git-add-able produced-in-container travel artifacts: dirty (untracked, modified, or
    staged) paths under any ``<manuscript>/rounds/`` tree, plus any ``*.nodemap.json`` sidecar.
    These are the round records/sidecars + instrumented maps a remote close must bank so the
    next local pull arrives warm (W6.2 banked-what-travels). Returns a sorted list the close
    reads and the orchestrator stages+commits; empty when nothing travel-eligible is pending.
    Read-only: like the rest of close_beats it NEVER stages or commits — it only enumerates.

    Empty ALSO when git did not answer — nothing can be enumerated from a tree that was
    never read. That case is not silent: the planner asks _dirty_paths itself and fires the
    beat fail-heavy with a why that names the unreadable git."""
    return _moved(_dirty_paths(repo) or set(), _TRAVEL_GLOBS)


def _wire_frontier_nonempty(repo) -> bool:
    """Is .wire_proposals.jsonl carrying an un-drained frontier? (Any non-blank
    line.) The wire-drain sub-step of the re-embed has nothing to do otherwise."""
    f = Path(repo) / ".wire_proposals.jsonl"
    try:
        if not f.is_file():
            return False
        return any(ln.strip() for ln in f.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return False


def _wire_ledgers_moved(repo, mark_epoch: Optional[float]) -> list[str]:
    """Which wire ledgers look touched since the mark. They're gitignored, so this
    is an mtime/existence heuristic, not a diff — explicit about that in the why."""
    moved: list[str] = []
    for name in _WIRE_LEDGERS:
        p = Path(repo) / name
        try:
            if p.is_file() and (mark_epoch is None or p.stat().st_mtime > mark_epoch):
                moved.append(name)
        except OSError:
            continue
    return moved


def _deposit_mode_note(repo, changed: set[str]) -> str:
    """The deposit's expected MODE, from what the close can see CHEAPLY. The persisted
    .meaning_tree.json (meaning_upfold's prev-state) is the one durable signal: present
    -> the deposit can take the INCREMENTAL path (cluster_residue_incremental reuses it);
    absent -> a cold FULL rebuild. The size of the changed set rides along as a coarse
    magnitude ONLY - the real churn>20% / lens-reshuffle / cluster-breach triggers that
    decide incremental-vs-full even WITH a tree present are measured by meaning_upfold at
    deposit time, never faked here (no precision we don't have)."""
    n = len(changed)
    if (Path(repo) / ".meaning_tree.json").is_file():
        return (f"deposit incremental expected (.meaning_tree.json present; {n} path(s) "
                "changed since the mark - coarse signal, real churn/reshuffle/breach "
                "measured at deposit time)")
    return (f"deposit full rebuild expected (no .meaning_tree.json - cold path; {n} path(s) "
            "changed since the mark)")


def _dream_beat() -> dict:
    """The day-dream, PLANNED not run (close_beats is a planner; the close ritual acts).
    Session-fact-shaped but GATED on the telemetry day-window: it fires iff events landed
    since the last day-dream marker (telemetry.last_dream_ts). The logging-precedes-any-dream
    law means the Sawbones log is already banked by the time this reads, so the count the
    dream would stitch is live. An UNRESOLVABLE marker (never dreamed) fires fail-heavy,
    mirroring beat_plan's no-mark law - we cannot bound the day, so we do not trust the
    count to gate. dream(grade=0) applies evidence-gated, REVERTIBLE lifecycle transitions;
    forge never auto-fires."""
    try:
        from laplace.engine import telemetry

        last = telemetry.last_dream_ts()
        n = len(telemetry.events_since_last_dream())
    except Exception as e:  # noqa: BLE001 - can't read the day-window -> fire fail-heavy
        return _entry("dream", True, ["laplace_dream"],
                      f"could not read the telemetry day-window ({e}) - fires fail-heavy")
    if last is None:
        return _entry(
            "dream", True, ["laplace_dream"],
            f"no day-dream marker yet - fires fail-heavy; {n} telemetry event(s) on record; "
            "dream(grade=0) applies evidence-gated lifecycle transitions (revertible); "
            "forge never auto-fires",
        )
    if n > 0:
        return _entry(
            "dream", True, ["laplace_dream"],
            f"{n} telemetry events since last day-dream {last} - dream(grade=0) applies "
            "evidence-gated lifecycle transitions (revertible); forge never auto-fires",
        )
    return _entry("dream", False, ["laplace_dream"],
                  f"no events since last day-dream {last} - nothing to stitch")


# --------------------------------------------------------------- the plan
def _entry(beat: str, fire: bool, sources, why: str) -> dict:
    return {"beat": beat, "fire": fire, "sources": list(sources), "why": why}


def beat_plan(repo, changed: Optional[set[str]] = None) -> list[dict]:
    """The graded close, as a list of ``{beat, fire, sources, why}``. ``changed``
    defaults to ``log_paths_since(mark) ∪ dirty`` — pass an explicit set to plan
    against a hypothetical diff. Grade-0 beats always fire; session-fact beats
    always fire (plainly flagged as not-diff-derivable); the rest fire iff their
    source map moved. An unresolvable mark fires everything (fail-heavy), and so
    does an unreadable dirty tree: both mean we cannot tell what moved, and the
    committed half alone (dulwich, independent of the git CLI) does not cover the
    uncommitted mid-session work the gate mostly exists for."""
    repo = Path(repo)
    mark = last_banked_close(repo)
    resolved = mark is not None
    mark_epoch = _mark_epoch(mark)
    since = f"since {mark}" if resolved else "since <no mark>"

    if changed is None:
        dirty = _dirty_paths(repo)
        git_blind = dirty is None
        changed = _changed_since(repo, mark) | (dirty or set())
    else:
        changed = set(changed)
        git_blind = False   # an explicit diff never consults git, so it is never blind
    blind_why = ("git unreadable — `git status` did not answer, so the dirty tree is unknown"
                 if git_blind else "no mark")

    plan: list[dict] = []

    # ---- grade-0: the trace that is banked every close, unconditionally ----
    for beat, src in (
        ("diary", ["EIGEN_DIARY.md"]),
        ("handoff", ["HANDOFF.md"]),
        ("session_handoff", ["SESSION_HANDOFF_<date>_*.md"]),
        ("commit", []),
        ("rehearsal", ["scripts/wake.py", "holdout/COLD_WAKE_QUESTIONS.md"]),
        ("open_stack_sweep", ["OPEN_STACK.md"]),
    ):
        plan.append(_entry(beat, True, src, "grade-0 trace — always"))

    # re-embed is grade-0; its wire-drain sub-step is conditional on a live frontier, and
    # its DEPOSIT half runs incremental-or-full by what the close can see cheaply (the
    # persisted .meaning_tree.json + the changed-set magnitude; real triggers at deposit time).
    drain = _wire_frontier_nonempty(repo)
    plan.append(_entry(
        "re-embed", True, ["scripts/reembed.py"],
        "grade-0 trace — always; wire-drain sub-step "
        + ("active (.wire_proposals.jsonl frontier non-empty)" if drain
           else "skipped (.wire_proposals.jsonl frontier empty)")
        + "; " + _deposit_mode_note(repo, changed),
    ))

    # ---- the weld smoke (W8.2): the interface weld's converged gate carries a FAST
    # subset (clauses 1 NAV-CLOSURE, 2 CONTEXT-CARRIES, 4 RAIL-MATCHES-DISK, 7 GOLDEN-
    # PAYLOADS) that every close re-runs, so the one surface on top of the machine can
    # never silently rot between welds. Grade-0-always (the standing-gate discipline —
    # the smoke is cheap and the weld is load-bearing): the source names the exact
    # `-k weld_smoke` shard, NEVER the flat suite. The planner only NAMES it; the close
    # ritual runs it (close_beats never runs a beat). ----
    plan.append(_entry(
        "weld_smoke", True,
        ["python -m pytest tests/test_interface_weld.py -k weld_smoke -q"],
        "grade-0 trace — always; the interface weld's fast converged subset "
        "(nav-closure, context-carries, rail-matches-disk, golden-payloads) "
        "smoked every close; never the flat suite, always the -k weld_smoke shard",
    ))

    # ---- session facts: real beats a diff structurally cannot derive ----
    for beat in ("standing_law", "sawbones_log"):
        plan.append(_entry(beat, True, [], "session fact — not diff-derivable"))

    # ---- the day-dream: session-fact-shaped, GATED on the telemetry day-window. Placed
    # AFTER sawbones_log because the logging-precedes-any-dream law means the Sawbones log
    # must already be banked before the dream reads its window (EIGEN_PROTOCOL.md Part C). ----
    plan.append(_dream_beat())

    # ---- diff-gated: fire iff the source map moved (or the mark is unresolvable) ----
    def gated(beat: str, globs: tuple[str, ...]) -> None:
        moved = _moved(changed, globs)
        fire = (not resolved) or git_blind or bool(moved)
        if not resolved or git_blind:
            why = f"{blind_why} — fires fail-heavy (watches {', '.join(globs)})"
        elif moved:
            why = f"fired: {', '.join(moved)} moved {since} (watches {', '.join(globs)})"
        else:
            why = f"unmoved {since} (watches {', '.join(globs)})"
        plan.append(_entry(beat, fire, globs, why))

    gated("architecture", _ARCH_GLOBS)
    gated("recurrence", _RECURRENCE_GLOBS)
    gated("durable_refs", _DURABLE_GLOBS)
    gated("seam_liveness", _SEAM_GLOBS)

    # effect_meter — gitignored ledgers, so mtime-vs-mark, not the diff.
    wire_moved = _wire_ledgers_moved(repo, mark_epoch)
    fire_effect = (not resolved) or bool(wire_moved)
    if not resolved:
        why_effect = "no mark — fires fail-heavy (gitignored wire ledgers, mtime heuristic)"
    elif wire_moved:
        why_effect = (
            f"fired: {', '.join(wire_moved)} mtime > mark (gitignored — mtime heuristic, {since})"
        )
    else:
        why_effect = f"wire ledgers unchanged {since} (gitignored — mtime heuristic)"
    plan.append(_entry("effect_meter", fire_effect, list(_WIRE_LEDGERS), why_effect))

    gated("holdout", _HOLDOUT_GLOBS)

    # ---- banked-what-travels (W6.2): the produced round records/sidecars + nodemaps to stage.
    # Driven by the DIRTY tree (untracked/modified), not the mark-diff — a freshly produced
    # remote round record is untracked, which the mark-diff cannot see; the beat LISTS them for
    # the orchestrator to git add + commit (the beat never stages). ----
    travel = banked_what_travels(repo)
    if travel:
        shown = ", ".join(travel[:12]) + (f" (+{len(travel) - 12} more)" if len(travel) > 12 else "")
        why_travel = (f"fired: {len(travel)} produced round record/sidecar/nodemap path(s) "
                      f"git-add-able — stage + commit so the next local pull arrives warm: {shown}")
    elif not resolved or git_blind:
        why_travel = (f"{blind_why} — fires fail-heavy (watches **/rounds/**, **/*.nodemap.json "
                      "for produced round records/sidecars/nodemaps to stage)")
    else:
        why_travel = ("no produced round records/sidecars/nodemaps pending "
                      "(watches **/rounds/**, **/*.nodemap.json)")
    plan.append(_entry("banked_what_travels", bool(travel) or not resolved or git_blind,
                       travel or list(_TRAVEL_GLOBS), why_travel))

    # ---- suite: NEVER flat — always the scoped shard; inherit green on a clean tree ----
    plan.append(_suite_beat(repo, changed, resolved, since, git_blind))

    return plan


def _suite_beat(repo, changed: set[str], resolved: bool, since: str,
                git_blind: bool = False) -> dict:
    """The suite is never run flat at close (the F20 covenant): always the scoped
    invocation over the changed nodes. An unresolvable mark fires it fail-heavy;
    a clean shard inherits the banked-green verdict (nothing moved, nothing rerun).
    An unreadable dirty tree fires it fail-heavy too — a clean shard is only an
    inherit when the tree it was computed from was actually read."""
    if not resolved:
        return _entry(
            "suite", True, [_SCOPED_SUITE],
            "no mark — fires fail-heavy; never the flat suite, always the scoped shard",
        )
    if git_blind:
        return _entry(
            "suite", True, [_SCOPED_SUITE],
            "git unreadable — the dirty tree could not be read, so an empty shard proves "
            "nothing; fires fail-heavy, never the flat suite, always the scoped shard",
        )
    try:
        from laplace.engine import tests_at_grade

        shard = tests_at_grade.test_shard(repo, changed=sorted(changed))
        files = list(shard.get("shard", []))
        untested = list(shard.get("untested_changes", []))
    except Exception as e:  # noqa: BLE001 - fall back to fire, never break the planner
        return _entry(
            "suite", True, [_SCOPED_SUITE],
            f"could not resolve the scoped shard ({e}) — firing the scoped invocation to be safe",
        )
    if not files:
        note = f"; untested changes: {', '.join(untested)}" if untested else ""
        return _entry(
            "suite", False, [_SCOPED_SUITE],
            f"clean shard {since} — inherits the banked-green verdict; never flat{note}",
        )
    return _entry(
        "suite", True, [_SCOPED_SUITE, *files],
        f"scoped shard {since}: {', '.join(files)}; never the flat suite",
    )
