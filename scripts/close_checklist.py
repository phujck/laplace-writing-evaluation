#!/usr/bin/env python3
"""close_checklist.py — the close ritual's MECHANICAL half, as one command.

EIGEN_PROTOCOL.md Part C walks five beats when Gerard says "sew up": (1) forks,
(2) retention, (3) soul, (4) Eigen's question, (5) bank the trace (Sawbones log,
diary, dated handoff, reembed, commit/push/PR) + the held-out prediction. Beats
1-4 need the author's judgment and cannot be mechanised — this script does not
try. It covers the mechanical tail of beat 5: did the trace actually get banked,
and are the standing hygiene instruments (recurrence, rotation, instrument-usage,
the holdout) clean or crying out.

WHAT THIS SCRIPT WILL NEVER DO, BY DESIGN:
  - It never writes, mutates, deletes, or reformats anything. It is a PURE
    REPORTER. Every "fix" it might suggest (rotate HANDOFF.md, mechanise a
    recurrence, score the holdout) is a separate, already-existing script the
    author or a later dispatch runs deliberately.
  - It never scores RETENTION (Part C beat 2 — "did this survive contact with
    the artifact?") or touches the SOUL (beat 3). Those are irreducibly the
    author's judgment call: only he can tell kept from bypassed, and soul/ is
    verbatim-or-nothing. Mechanising either would replace a judgment with a
    metric that gets gamed. This is not a gap to fill later — it is a boundary.

CHECKS (each PASS / WARN / FAIL + one-line detail):
  git_state             clean tree or enumerated dirt; unpushed commit count
  gitignore_forward_law any .gitignore rule ADDED since the last close with no
                         rebuild lane (ensure_state entry / surfacing_audit
                         backstop) — the gitignore-forward-law surfaced as a WARN.
                         RW-20260713-211452-733024 reserved the exact gate SHAPE
                         to the author, so this is advisory only, never a gate.
  recurrence            scripts/detect_recurrence.py --check (unmechanised
                         friction clusters — the correction that keeps recurring)
  durable_refs          scripts/check_durable_refs.py (ephemeral paths cited on a
                         durable surface — its FAIL maps to WARN advisory here)
  claim_checks          scripts/run_claim_checks.py (the banked CHECK predicates in
                         AUDIT_*.md — a drifted claim's FAIL maps to WARN advisory here)
  seam_liveness         scripts/audit_silent_failures.py (the silent-failure seams
                         between pipeline organs — always advisory, never a gate)
  effect_meter          scripts/audit_effect_meter.py --table (an always-rc-0
                         measurement, surfaced as a reading — never a WARN gate)
  rotation              scripts/rotate_handoff.py --dry-run (is HANDOFF.md over
                         budget and due to roll?)
  handoff_freshness     does HANDOFF.md's latest "## ⟶" section carry today's
                         date?
  session_handoff_dated does a dated SESSION_HANDOFF_<today>*.md exist?
  open_stack_sweep      does OPEN_STACK.md carry a sweep section dated today, AND does
                         that section's body carry the typed completeness marker
                         (`swept: complete`) rather than admitting deferral? (AUDIT_
                         2026-07-15 §B2 — a dated header alone proves the sweep
                         happened, never that it was thorough.) PASS on the marker,
                         FAIL on an admitted deferral (quoting the phrase), WARN when
                         a dated section states neither.
  supersede_sweep       scripts/supersede_sweep.py --gate (AUDIT_2026-07-15 §B3 — is
                         every citation of a superseded marker in the durable corpus
                         HAND-stamped SUPERSEDED?). WARN-tier, mirroring claim_checks:
                         a nonzero gate WARNs, never FAIL_ELIGIBLE (FAIL-promotion is
                         the author's later ruling). The close only ever runs --gate
                         (read-only); --fix (which writes stamps into the durable
                         corpus) stays a deliberate, by-hand step, never auto-run here.
  instrument_usage      any PROXY_RESOLUTIONS_ / DECISION_ / DREAM_AUDIT_ file
                         from the current session-cluster that no later dated
                         doc (a newer SESSION_HANDOFF, HANDOFF.md, OPEN_STACK.md,
                         EIGEN_DIARY.md) ever mentions by name — the b-proxy-first
                         class: an instrument built and never opened. One WARN
                         per orphaned instrument; this check never FAILs (a
                         string-match miss doesn't prove non-consumption, so it
                         can only ever be advisory, never a gate).
  holdout               holdout/PREDICTION_pending.json newer than the newest
                         holdout/SCORED_*.json — an outstanding held-out
                         prediction still awaiting next wake's scoring.
  fork_drain            THE STANDING DRAIN (his ruling PV-20260717T002125 item 4 —
                         "every close, automatically"): parked forks DRAFTED via
                         fork_adjudicator.drive(dry-run) → the dispatch manifest emitted
                         (0 ledger writes) → REVIEW owed on the /desk forks lane → BANK
                         via --live, the supervised final step, behind the reviewed path.
                         WARN per parked fork; the close NEVER banks. GENUINELY-HIS routed
                         counts as decided (his exception). Advisory only.
  first_chair           FAIL_ELIGIBLE — THE FIRST-CHAIR CLAUSE (the infrastructure law):
                         a working tree carrying a produced artefact (pdf / minted /
                         rebuilt src/laplace/*.html surface) MUST carry a banked
                         evidence/FIRST_CHAIR_*.md note NEWER than that artefact — the
                         orchestrator's non-delegable read of what shipped. Missing or
                         stale note FAILs the close (evidence/FIRST_CHAIR_2026-07-17_
                         seam5.md is the shape).
  fork_adjudication     OPEN_STACK's live 🔴 forks that no proxy_verdicts.jsonl
                         entry references — a fork PARKED, not adjudicated. WARN
                         per un-adjudicated fork (the FORK-LAW amendment: a
                         derivable fork is unfinished work, never re-deferred
                         without a verdict; a GENUINELY-HIS verdict counts as
                         adjudicated — routed to him, not parked). PASS when all
                         live forks are adjudicated-or-routed. Advisory only.
  unseal_follow_through archive/soul_dump/ carries files untracked by git — the
                         unseal verdict says commit the raw/distillate. Only fires
                         where the raw exists (his local machine). Advisory only.
  cold_wake_coverage    rebuilds the grade-0 (engine + person)/1/2 hello payloads
                         in-process and scores them against
                         holdout/COLD_WAKE_QUESTIONS.md via laplace.engine.cold_probe —
                         the rehearsal's mechanical half: the writer of a trace
                         must pass the reader's test before it's banked. WARN-only
                         v1; not yet FAIL_ELIGIBLE.
  claude_md_render      scripts/render_claude_md.py --check against the committed
                         CLAUDE.md — a hand-edited or stale ambient file is a
                         corrupted banked artifact. WARNs (not FAILs) while the
                         renderer is still landing.
  friction_drain        scripts/drain_frictions.py --report (READ-ONLY): the
                         friction drain's REPORT half — open/consumed friction
                         counts + the residual tally of findings that exist SOLELY
                         as raw FEEDBACK appends (never drained through the ledger
                         door). WARN when that tally is nonzero. The close only
                         reads; the drain's draft/apply halves stay manual.
  feedback_append_guard the grep-guard: WARNs LOUDLY if a raw FEEDBACK-append call
                         site reappears on the HARNESSED pour path
                         (.claude/workflows/*.js). project-fixedpoint.js's lock
                         tier is the ONE whitelisted fix_mode=loop exception.
  register              scripts/audit_register.py: the register conjugate — re-scans
                         the rule-bearing surfaces for the register-law tic lexicon and
                         compares per-file totals to corpus_friction/register_baseline.
                         json. WARN when any file rises above baseline (a new tic);
                         advisory only, never a gate.
  aging_teeth           FAIL_ELIGIBLE — THE AGING TEETH (W-TEETH, PV-20260722T165050Z, his
                         verbatim law: loops left open fossilize; an aged ask is a destroyed
                         decision; "carried, named" must stop being free). Shells out to
                         scripts/ledger_age_audit.py: every OPEN row in the accumulating
                         ledgers (work_orders / promises / open_stack_forks) past its class
                         max quiet age (author-gated 3d / machine 14d) must carry a dated
                         defer with an owner (the defer_until/deferred_by note idiom) or the
                         close FAILs naming the rows. his-direction covenant promises are
                         EXEMPT (carried-not-collected per contract/README.md) but named; a
                         fork's trigger is its native condition-defer.
  landing_sweep         WARN-tier — THE LANDING SWEEP (W-TEETH): an OPEN work-order whose
                         work has LANDED (a file it names touched, or its action slug in a
                         commit subject, since the last banked close) but was never resolved
                         through the evidence door — the census's landed-but-open class. WARN,
                         not FAIL: a name-match is a heuristic, not proof the work is done.
  fence_rate            WARN-tier — the fence meter (step 2 of DECISION_2026-08-17_fence-
                         promotion-sequencing.md). Feeds the landing sweep's candidate ids
                         into laplace.engine.reconstruction_fence.false_negative_report: of the
                         work-orders whose work landed, how many did a banked probe name at
                         the authoring moment? The row prints the caught ids, the missed
                         ids, and the rate. With no landed candidate to diff against the
                         rate is undefined rather than 0.0 — an empty denominator would read
                         as a perfect score. Advisory by decision, never FAIL_ELIGIBLE: the
                         store-faithfulness work orders come first, and FAIL then arrives
                         per surface on that surface's own measured precision.

VERDICT: rc=1 only when a FAIL fires (handoff_freshness / session_handoff_dated /
open_stack_sweep / claude_md_render / portable_paths / first_chair / contact_law /
orphan_census / scroll_law / register_zero / aging_teeth / open_stack_render /
metric_currency / holdout — i.e. a trace artifact the
close is supposed to bank is missing or stale, a produced artefact would ship unread, or
an open ledger row is riding silently past its max quiet age). The last three joined at the
thin-systems audit (2026-08-17): a render whose own generated banner already CLAIMS to fail
the close, the deposit's banked metric verdict when its gate DECLINED, and the author's
held-out prediction when the surface it names actually broke (rc 1; rc 3 — refused to grade —
stays WARN). Every other check is advisory:
it can WARN, never FAIL, and never moves the exit code. The last line of
output is always the sentinel
(tonight's convention, scripts/paper_gates.py):
    VERDICT=PASS warns=<n>
    VERDICT=FAIL checks=<n_fail>/<n_total> reasons=<comma,list> warns=<n>
so a truncated read (tail -1) still carries the whole verdict.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_probe import REFUSAL_EXIT  # noqa: E402

# The only checks allowed to ever return FAIL (see module docstring). Enforced
# by an assertion in _verdict, not just documented, so a future check that
# forgets itself and returns FAIL can't silently start gating the exit code.
FAIL_ELIGIBLE = {"handoff_freshness", "session_handoff_dated", "open_stack_sweep",
                 "claude_md_render", "portable_paths", "first_chair", "contact_law",
                 "orphan_census", "scroll_law", "register_zero", "aging_teeth",
                 # the thin-systems audit's two close gates (2026-08-17): a render whose own
                 # banner already CLAIMS to fail the close, and the deposit's own banked
                 # metric verdict (a DECLINE that used to be a print with no promotion path).
                 "open_stack_render", "metric_currency", "holdout"}

# The bounded close fires these checks on every run. The three excluded checks own
# heavyweight executions: contact_law and orphan_census are pytest shards selected by
# sewup's code floor, while scroll_law is an explicit browser walk. Keeping those
# executions out of this reader avoids paying for the same tests twice.
FAST_FAIL_ELIGIBLE = FAIL_ELIGIBLE - {"contact_law", "orphan_census", "scroll_law"}

#: THE REAPER'S SCROLL-LAW WALK (PRM-20260721-liveness-law / THE SCROLL LAW, P10 as
#: amended 2026-07-21): the browser the chair-walk drives. When it (or Playwright) is
#: absent the scroll-law clause SKIPS WITH A NAMED REASON (WARN, never a silent pass) —
#: a close on a headless box cannot walk, but it says so out loud. The actual chromium
#: binary is resolved by chair_walk_scroll_law.py's own _chrome_path() (platform
#: candidates -> PATH -> Playwright's bundled chromium); WO-20260820-excise-the-
#: restriction-era-bloat removed this file's own restriction-era pre-check pin
#: (/opt/pw-browsers/..., a vendored-container path absent on the permanent box) that
#: was duplicating and getting that resolution wrong.
#: the FAIL-eligible roster the scroll walk GATES at close (the shell's own surfaces the
#: reaper can hold green). A breach on any of these FAILs the close.
#:
#: /guide is DEFERRED to the advisory list below (walked, screenshotted, and reported —
#: but NOT in the FAIL-eligible gate) with a named reason: the /guide surface
#: (src/laplace/web/guide.html + static_shared/guide-panes.mjs — the W-guide leg's files, NOT
#: the reaper's) renders one long document that grows the whole page, breaching P10's
#: page-level bound (~11.5x viewport, scroll_h~10377 @1280x900; driven twice — the repair
#: verifier's own Playwright drive + evidence/scroll_law_close_walk/verdict.json). The
#: reaper owns none of the guide surface files, so it cannot land the bounded-pane fix; the
#: exact patch is filed for the guide-surface owner (this repair round's
#: needs_outside_ownership + the census §9 owed-fix row). /guide re-enters
#: _SCROLL_WALK_GATED_ROUTES the moment that leg lands bounded pane scroll. This is the
#: register-zero-disarmed idiom applied PER ROUTE: named, tracked, owed — never silently
#: swallowed. The close output names the /guide breach every run, so nothing is hidden; it
#: simply does not FAIL the exit code on a surface another leg must fix.
_SCROLL_WALK_GATED_ROUTES = "/,/desk,/pipeline,/storyboard,/artefact,/conceptric,/altitude,/analytics,/assets,/map"
#: walked WARN-only (advisory), each with a named owed-fix reason. A breach here is
#: REPORTED LOUDLY in the clause detail but never FAILs the close — another leg's surface
#: to fix. Remove a route from here (fold it back into the gated roster) the moment its
#: owning leg lands bounded pane scroll.
_SCROLL_WALK_ADVISORY_ROUTES = "/guide"
_SCROLL_WALK_PROJECTS = "paper_falqon,eigenengine"

#: THE FIRST-CHAIR CLAUSE (THE INFRASTRUCTURE LAW, ARMING_2026-07-16): a produced
#: artefact — a compiled PDF, a minted output, a rebuilt served surface — is exactly the
#: class the orchestrator must READ before it ships (his ruling: the first chair is
#: non-delegable). A working tree carrying such an artefact with no fresh
#: evidence/FIRST_CHAIR_*.md note is an artefact banked UNREAD — the close FAILs it.
#: evidence/FIRST_CHAIR_2026-07-17_seam5.md is the note's shape.
FIRST_CHAIR_ARTEFACT_SUFFIXES = (".pdf",)
FIRST_CHAIR_ARTEFACT_SUBSTRINGS = ("minted",)
#: a rebuilt SERVED SURFACE — the served HTML pages (a surface rebuild is a produced
#: artefact per the arming). Matched as ``src/laplace/<name>.html`` at any depth.
_SURFACE_HTML_RE = re.compile(r"(?:^|/)src/laplace/[^/]+\.html$")
_FIRST_CHAIR_GLOB = "FIRST_CHAIR_*.md"

#: the Windows/NTFS-illegal filename characters — the exact set no tracked path
#: may contain (friction RW-20260713-203140-001240: a colon in a banked filename
#: aborts the author's local pull). Mirrors laplace.pipeline.pathsafe.ILLEGAL_PATH_CHARS
#: (the sid->filename encoder's char set); kept as a bare literal here so the gate
#: is a pure git+string scan that never needs laplace on the path to fire.
NTFS_ILLEGAL_PATH_CHARS = ':*?"<>|'

INSTRUMENT_PATTERNS = ("PROXY_RESOLUTIONS_", "DECISION_", "DREAM_AUDIT_")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# the OPEN_STACK live-fork legend + F-id shape now live with the shared enumeration
# (laplace.pipeline.fork_adjudicator), which check_fork_adjudication consumes.


@dataclass
class Check:
    name: str
    status: str  # PASS | WARN | FAIL
    detail: str


def _run(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[Optional[int], str, str]:
    """Run a subprocess, never raising: (returncode, stdout, stderr).
    returncode is None if the executable/script could not even be launched."""
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",  # Windows: cp1252 default chokes on unicode paths
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "", str(exc)


def _extract_date(name: str) -> Optional[str]:
    m = DATE_RE.search(name)
    return m.group(1) if m else None


# ---------------------------------------------------------------- (a) git state
def check_git_state(repo: Path) -> Check:
    rc, out, err = _run(["git", "status", "--porcelain"], repo)
    if rc is None:
        return Check("git_state", "WARN", f"git unavailable: {err.strip()}")
    if rc != 0:
        return Check("git_state", "WARN", f"git status failed: {err.strip()}")
    dirty_lines = [ln for ln in out.splitlines() if ln.strip()]
    n_dirty = len(dirty_lines)

    # unpushed commits vs upstream, if one is configured
    rc_up, upstream, _ = _run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], repo
    )
    unpushed = None
    if rc_up == 0 and upstream.strip():
        rc_cnt, cnt_out, _ = _run(
            ["git", "rev-list", "--count", f"{upstream.strip()}..HEAD"], repo
        )
        if rc_cnt == 0 and cnt_out.strip().isdigit():
            unpushed = int(cnt_out.strip())

    if n_dirty == 0 and (unpushed is None or unpushed == 0):
        detail = "clean tree"
        if unpushed is None:
            detail += ", no upstream configured"
        else:
            detail += ", 0 unpushed"
        return Check("git_state", "PASS", detail)

    parts = []
    if n_dirty:
        parts.append(f"{n_dirty} dirty path(s)")
    if unpushed:
        parts.append(f"{unpushed} unpushed commit(s)")
    if unpushed is None:
        parts.append("no upstream configured")
    return Check("git_state", "WARN", ", ".join(parts) or "dirty")


# --------------------------------------------------------- (b) unmechanised recurrence
def check_recurrence(repo: Path) -> Check:
    script = repo / "scripts" / "detect_recurrence.py"
    if not script.exists():
        return Check("recurrence", "WARN", "scripts/detect_recurrence.py not found")
    rc, _out, err = _run([sys.executable, str(script), "--check"], repo)
    if rc is None:
        return Check("recurrence", "WARN", f"could not run detect_recurrence.py: {err.strip()}")
    if rc == 0:
        return Check("recurrence", "PASS", "no unmechanised recurrence")
    if rc == 1:
        # best-effort: pull the count for a friendlier detail; never fatal if it fails
        count_detail = "recurrence found (--check exit 1)"
        # detect_recurrence.py's plain (non --check) run also exits 1 when it
        # finds recurrences (its exit code always mirrors recurrence_count>0,
        # --check just suppresses the JSON body) — so parse on stdout content,
        # not on this second call's own rc.
        _rc2, out2, _ = _run([sys.executable, str(script)], repo)
        try:
            report = json.loads(out2)
            count_detail = (
                f"{report.get('recurrence_count', '?')} unmechanised recurrence "
                f"cluster(s) across {len(report.get('ledgers', []))} ledger(s)"
            )
        except (json.JSONDecodeError, AttributeError):
            pass
        return Check("recurrence", "WARN", count_detail)
    return Check("recurrence", "WARN", f"detect_recurrence.py --check exited {rc}: {err.strip()}")


# ------------------------------------------------- (b2) durable-refs / seams / effect
# Three advisory instruments the close surfaces but never gates on. Each shells out
# the same way check_recurrence does; none is FAIL_ELIGIBLE, so a red instrument
# WARNs here, it does not move the exit code.
def check_durable_refs(repo: Path) -> Check:
    script = repo / "scripts" / "check_durable_refs.py"
    if not script.exists():
        return Check("durable_refs", "WARN", "scripts/check_durable_refs.py not found")
    rc, out, err = _run([sys.executable, str(script)], repo)
    if rc is None:
        return Check("durable_refs", "WARN", f"could not run check_durable_refs.py: {err.strip()}")
    if rc == 0:
        return Check("durable_refs", "PASS", "no ephemeral-path refs on durable surfaces")
    # check_durable_refs FAILs (rc=1) on a leak; here that maps to WARN — a
    # durable-ref leak is a close-time thing to see, not a mechanical gate.
    tail = out.strip().splitlines()[-1] if out.strip() else f"rc={rc}"
    return Check("durable_refs", "WARN", f"ephemeral-path refs found (advisory): {tail}")


def check_claim_checks(repo: Path) -> Check:
    """The banked-claim CHECK predicates (AUDIT_*.md), re-run at close so a drifted claim expires
    LOUDLY rather than waiting for a scout to rediscover it. Shells out to run_claim_checks.py the
    same way check_durable_refs does; a FAIL there maps to WARN here — new instrument, advisory
    only, never FAIL_ELIGIBLE (it earns teeth later)."""
    script = repo / "scripts" / "run_claim_checks.py"
    if not script.exists():
        return Check("claim_checks", "WARN", "scripts/run_claim_checks.py not found")
    rc, out, err = _run([sys.executable, str(script)], repo)
    if rc is None:
        return Check("claim_checks", "WARN", f"could not run run_claim_checks.py: {err.strip()}")
    tail = next((ln.strip() for ln in reversed(out.splitlines()) if ln.startswith("VERDICT=")), "")
    if rc == 0:
        return Check("claim_checks", "PASS", tail or "all banked CHECK predicates hold")
    return Check("claim_checks", "WARN", f"banked claim drifted (advisory): {tail or f'rc={rc}'}")


def check_supersede_sweep(repo: Path) -> Check:
    """AUDIT_2026-07-15 §B3: ruling supersession is prose almost everywhere; supersede_sweep.py
    was advisory-only (rc always 0). Its new --gate mode turns the unstamped-citation report
    into a pass/fail signal; this check shells out to it the same way check_claim_checks does
    and enters the close at the SAME WARN tier (the house pattern claim-checks used) — a
    nonzero gate WARNs here, it never FAIL_ELIGIBLE (FAIL-promotion is the author's later
    ruling, banked in the audit, not mechanised in this session). The close only ever runs
    --gate (read-only); --fix, which writes SUPERSEDED stamps into the durable corpus, is
    deliberately never invoked from here — fixing the corpus automatically is his call."""
    script = repo / "scripts" / "supersede_sweep.py"
    if not script.exists():
        return Check("supersede_sweep", "WARN", "scripts/supersede_sweep.py not found")
    rc, out, err = _run([sys.executable, str(script), "--gate"], repo)
    if rc is None:
        return Check("supersede_sweep", "WARN", f"could not run supersede_sweep.py --gate: {err.strip()}")
    tail = next((ln.strip() for ln in reversed(out.splitlines()) if ln.startswith("VERDICT=")), "")
    if rc == 0:
        return Check("supersede_sweep", "PASS", tail or "no unstamped superseded-marker citations")
    return Check(
        "supersede_sweep", "WARN",
        f"unstamped superseded-marker citation(s) (advisory): {tail or f'rc={rc}'}",
    )


def check_seam_liveness(repo: Path) -> Check:
    script = repo / "scripts" / "audit_silent_failures.py"
    if not script.exists():
        return Check("seam_liveness", "WARN", "scripts/audit_silent_failures.py not found")
    rc, out, err = _run([sys.executable, str(script)], repo)
    if rc is None:
        return Check("seam_liveness", "WARN", f"could not run audit_silent_failures.py: {err.strip()}")
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    m = re.search(r"warns=(\d+)", tail)
    n_warn = int(m.group(1)) if m else 0
    if rc == 0 and n_warn == 0:
        return Check("seam_liveness", "PASS", "no live seam warnings")
    return Check("seam_liveness", "WARN", f"seam audit: {tail or f'rc={rc}'}")


def check_effect_meter(repo: Path) -> Check:
    script = repo / "scripts" / "audit_effect_meter.py"
    if not script.exists():
        return Check("effect_meter", "WARN", "scripts/audit_effect_meter.py not found")
    rc, out, err = _run([sys.executable, str(script), "--table"], repo)
    if rc is None:
        return Check("effect_meter", "WARN", f"could not run audit_effect_meter.py: {err.strip()}")
    # An always-rc-0 measurement, surfaced (never a WARN gate): its first summary
    # line is the table header carrying the headline reading.
    summary = next((ln.strip() for ln in out.splitlines() if "AUDIT-EFFECT METER" in ln), "")
    return Check("effect_meter", "PASS", summary or "ran (no summary line parsed)")


# ------------------------------------------------------------------ (c) rotation
def check_rotation(repo: Path) -> Check:
    script = repo / "scripts" / "rotate_handoff.py"
    if not script.exists():
        return Check("rotation", "WARN", "scripts/rotate_handoff.py not found")
    handoff = repo / "HANDOFF.md"
    if not handoff.exists():
        return Check("rotation", "WARN", "HANDOFF.md not found")
    rc, out, err = _run([sys.executable, str(script), "--file", str(handoff), "--dry-run"], repo)
    if rc is None:
        return Check("rotation", "WARN", f"could not run rotate_handoff.py: {err.strip()}")
    if rc != 0:
        return Check("rotation", "WARN", f"rotate_handoff.py --dry-run exited {rc}: {err.strip()}")
    m_roll = re.search(r"arrow sections roll:\s*(\d+)\s*\(([\d,]+)\s*bytes\)", out)
    m_size = re.search(r"current size:\s*([\d,]+)\s*bytes", out)
    n_roll = int(m_roll.group(1)) if m_roll else 0
    size = m_size.group(1) if m_size else "?"
    if n_roll > 0:
        return Check(
            "rotation", "WARN",
            f"rotation due: HANDOFF.md is {size} bytes, {n_roll} section(s) rollable",
        )
    return Check("rotation", "PASS", f"HANDOFF.md is {size} bytes, within budget")


# ---------------------------------------------------------- (d) HANDOFF freshness
def check_handoff_freshness(repo: Path, today: str) -> Check:
    handoff = repo / "HANDOFF.md"
    if not handoff.exists():
        return Check("handoff_freshness", "FAIL", "HANDOFF.md not found")
    text = handoff.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^## ⟶.*?\((\d{4}-\d{2}-\d{2})", text, re.M)
    if not m:
        return Check("handoff_freshness", "FAIL", "no dated '## ⟶' section found in HANDOFF.md")
    latest = m.group(1)
    if latest == today:
        return Check("handoff_freshness", "PASS", f"latest section dated {latest}")
    return Check(
        "handoff_freshness", "FAIL",
        f"latest section dated {latest}, expected {today} — HANDOFF.md not yet updated",
    )


# ---------------------------------------- (d1b) probe-before-claim on plan surfaces
def check_probe_before_claim(repo: Path) -> Check:
    """The structural guard for the 2026-07-16 hedge-outranks-banked-state class
    (RW-20260716-144235-142690): environmental claims in plan-class documents being
    banked this session must cite a probe, not a guess. WARN-tier always (the exact
    gate shape stays the author's) — mirrors claim_checks."""
    script = repo / "scripts" / "audit_probe_before_claim.py"
    if not script.exists():
        return Check("probe_before_claim", "WARN", "audit_probe_before_claim.py not found")
    rc, out, err = _run([sys.executable, str(script)], repo)
    if rc is None:
        return Check("probe_before_claim", "WARN", f"could not run: {err.strip()}")
    if rc == 0:
        detail = out.strip().splitlines()[-1] if out.strip() else "clean"
        return Check("probe_before_claim", "PASS", detail)
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return Check("probe_before_claim", "WARN",
                 f"{lines[0] if lines else 'findings'} (advisory — cite probes or ratify)")


# ------------------------------------------- (d2) the ingest conjugate-write fired
def check_ledger_freshness(repo: Path, today: str) -> Check:
    """Did the close route the residual through ``self_corpus.ingest()``?

    The write half of continuity-as-reconstruction: hand-writing HANDOFF/DIARY while
    skipping ``ingest()`` froze CONCEPTRIC_LEDGER.md for 6 days (07-13 → 07-19, the
    consolidation's C02) — the read half cannot compensate for a missing write half.
    PASS = the ledger carries an ``at:``-stamped ingest entry dated today; WARN when
    the newest stamp is stale or no stamped entry exists yet (entries predating the
    2026-07-19 ``at:`` stamp are unparseable for freshness — advisory, never a hard
    gate on old history)."""
    ledger = repo / "CONCEPTRIC_LEDGER.md"
    if not ledger.exists():
        return Check("ledger_freshness", "WARN", "CONCEPTRIC_LEDGER.md not found")
    text = ledger.read_text(encoding="utf-8", errors="replace")
    stamps = re.findall(r"<!-- ingest grade:\d+ kind:\w+ at:(\d{4}-\d{2}-\d{2}) -->", text)
    if not stamps:
        return Check(
            "ledger_freshness", "WARN",
            "no at:-stamped ingest entry — route this close's residual through "
            "self_corpus.ingest() (scripts/ingest_residual.py)")
    latest = max(stamps)
    if latest == today:
        return Check("ledger_freshness", "PASS", f"ingest fired today ({latest})")
    return Check(
        "ledger_freshness", "WARN",
        f"newest ingest stamp {latest} != {today} — the conjugate write has not "
        "fired this close (scripts/ingest_residual.py)")


# --------------------------------------------------- (e) dated SESSION_HANDOFF exists
def check_session_handoff_dated(repo: Path, today: str) -> Check:
    matches = sorted(repo.glob(f"SESSION_HANDOFF_{today}*.md"))
    if matches:
        return Check(
            "session_handoff_dated", "PASS",
            f"{len(matches)} file(s): {', '.join(p.name for p in matches)}",
        )
    return Check(
        "session_handoff_dated", "FAIL",
        f"no SESSION_HANDOFF_{today}*.md found",
    )


# --------------------------------------------------- (f) OPEN_STACK sweep dated today
# AUDIT_2026-07-15 §B2: a dated ``## <today> sweep`` header alone PASSed even on a section
# whose own prose admitted "the full row-sweep deferred AGAIN" — existence and completeness
# are mechanically indistinguishable on the header alone. The fix reads the section BODY (to
# the next ``## `` header or EOF) for a typed completeness marker instead of trusting the
# dated header: PASS only on the literal ``swept: complete`` token; a body that instead
# admits ``deferred``/``deferral`` FAILs, quoting the offending phrase; a dated header with
# NEITHER token WARNs, naming the reason (this check stays FAIL_ELIGIBLE — see
# check_claude_md_render for the precedent of a FAIL_ELIGIBLE check that also uses WARN for
# an intermediate/uncertain read). Undated / missing-file behaviour is unchanged.
_SWEEP_COMPLETE_RE = re.compile(r"swept:\s*complete", re.I)
_SWEEP_DEFERRAL_RE = re.compile(r"\bdeferr(?:ed|al)\b", re.I)


def _sweep_section_body(text: str, header_end: int) -> str:
    """The dated sweep section's body: from just after the matched header to the next
    ``## `` (a true line-start header) or EOF."""
    rest = text[header_end:]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def check_open_stack_sweep(repo: Path, today: str) -> Check:
    open_stack = repo / "OPEN_STACK.md"
    if not open_stack.exists():
        return Check("open_stack_sweep", "FAIL", "OPEN_STACK.md not found")
    text = open_stack.read_text(encoding="utf-8", errors="replace")
    m = re.search(rf"^## {re.escape(today)}[a-z]?\s+sweep", text, re.M)
    if not m:
        return Check(
            "open_stack_sweep", "FAIL",
            f"no '## {today}[ ]sweep' section found in OPEN_STACK.md",
        )

    body = _sweep_section_body(text, m.end())
    sweep_complete = bool(_SWEEP_COMPLETE_RE.search(body))
    if sweep_complete:
        return Check("open_stack_sweep", "PASS", f"found: {m.group(0)} — swept: complete")

    dm = _SWEEP_DEFERRAL_RE.search(body)
    if dm:
        line_start = body.rfind("\n", 0, dm.start()) + 1
        line_end = body.find("\n", dm.start())
        line_end = len(body) if line_end == -1 else line_end
        phrase = body[line_start:line_end].strip()[:200]
        return Check(
            "open_stack_sweep", "FAIL",
            f"dated header found ({m.group(0)}) but the section body admits deferral, "
            f"not completeness: \"{phrase}\" — stamp `swept: complete` when the sweep "
            "genuinely finishes (existence and completeness are mechanically distinct)",
        )

    return Check(
        "open_stack_sweep", "WARN",
        f"found: {m.group(0)} — completeness unstated: stamp `swept: complete` "
        "or name the deferral",
    )


# ----------------------------------------------------------- (g) instrument usage
def _last_dated_handoff(repo: Path) -> Optional[tuple[str, Path]]:
    """(date, path) of the most recent SESSION_HANDOFF_<date>*.md, by filename
    date first, mtime second, filename third (all tie-breaks best-effort — see
    module docstring on why perfect same-day ordering isn't mechanically knowable)."""
    candidates = []
    for p in repo.glob("SESSION_HANDOFF_*.md"):
        d = _extract_date(p.name)
        if d:
            candidates.append((d, p.stat().st_mtime, p.name, p))
    if not candidates:
        return None
    candidates.sort()
    d, _mtime, _name, p = candidates[-1]
    return d, p


def check_instrument_usage(repo: Path, today: str) -> list[Check]:
    last = _last_dated_handoff(repo)
    cutoff_date = last[0] if last else None

    instruments = []
    for pattern in INSTRUMENT_PATTERNS:
        for p in repo.glob(f"{pattern}*.md"):
            d = _extract_date(p.name)
            if d and (cutoff_date is None or d >= cutoff_date):
                instruments.append((d, p))

    if not instruments:
        return [Check("instrument_usage", "PASS", "no in-scope instrument files")]

    # dated docs an instrument could plausibly be "consumed" by: later
    # SESSION_HANDOFF files, plus the three living, continuously-rewritten docs.
    living_docs = [repo / n for n in ("HANDOFF.md", "OPEN_STACK.md", "EIGEN_DIARY.md")]
    session_handoffs = list(repo.glob("SESSION_HANDOFF_*.md"))

    results = []
    for d, inst in instruments:
        stem = inst.stem
        referenced = False
        candidate_docs = [doc for doc in living_docs if doc.exists()]
        candidate_docs += [
            sh for sh in session_handoffs
            if sh != inst and (_extract_date(sh.name) or "") >= d
        ]
        for doc in candidate_docs:
            try:
                if stem in doc.read_text(encoding="utf-8", errors="replace"):
                    referenced = True
                    break
            except OSError:
                continue
        if referenced:
            results.append(Check("instrument_usage", "PASS", f"{inst.name}: referenced"))
        else:
            results.append(
                Check(
                    "instrument_usage", "WARN",
                    f"{inst.name}: instrument built, never consumed (no later dated doc references it)",
                )
            )
    return results


# ------------------------------------------------------------------- (h) holdout
_RC_RE = re.compile(r"rc=(-?\d+)")


def check_holdout(repo: Path) -> Check:
    """FAIL_ELIGIBLE (WO-20260817-holdout-scores-deposit, the thin-systems audit 2026-08-17) —
    READS THE VERDICTS, not the mtimes. This check used to compare PREDICTION_pending.json's
    mtime against the newest SCORED_*.json's and could therefore only ever WARN: the wake was
    scoring the author's verbatim holdout, PRINTING FAIL, and the close had nothing to read, so
    a broken surface and a fresh timestamp were indistinguishable. Now the wake banks what it
    scored (holdout.LAST_SCORE) and this reads it.

    THE VERDICT SPACE IS THREE. rc 1 (a graded fail) means the surface actually BROKE -> FAIL.
    rc 3 (service_probe.REFUSAL_EXIT: playwright absent, no browser, nothing listening) means
    the probe REFUSED TO GRADE -> WARN naming the missing dependency, never a FAIL and never a
    pass. BUDGET/UNPAYABLE (the wall) and an absent deposit are the same UNPROVEN tier: WARN."""
    holdout = repo / "holdout"
    pending = holdout / "PREDICTION_pending.json"
    if not pending.exists():
        return Check("holdout", "PASS", "no PREDICTION_pending.json outstanding")
    last = holdout / "LAST_SCORE.json"
    if not last.is_file():
        return Check("holdout", "WARN",
                     "a prediction is pending and no wake on this machine has banked a "
                     "scorecard for it yet (holdout/LAST_SCORE.json absent) — UNPROVEN, "
                     "not a pass")
    try:
        card = json.loads(last.read_text(encoding="utf-8"))
        pend = json.loads(pending.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Check("holdout", "WARN", f"could not read the holdout scorecard: {exc}")
    if card.get("banked") and pend.get("banked") and card["banked"] != pend["banked"]:
        return Check("holdout", "WARN",
                     f"the banked scorecard grades the prediction of {card['banked']}, but the "
                     f"pending one was banked {pend['banked']} — a newer prediction is awaiting "
                     "its first scoring wake")
    results = card.get("mechanical") or []
    if not results:
        return Check("holdout", "WARN",
                     "the last scorecard graded no mechanical checks — nothing measured")

    def _rc(r: dict) -> Optional[int]:
        m = _RC_RE.search(str(r.get("detail") or ""))
        return int(m.group(1)) if m else None

    broke, unrunnable, unpaid, passed = [], [], [], []
    for r in results:
        rid, verdict = str(r.get("id", "?")), str(r.get("verdict"))
        if verdict == "PASS":
            passed.append(rid)
        elif verdict in ("BUDGET", "UNPAYABLE"):
            unpaid.append(rid)
        elif verdict == "ERROR" or _rc(r) == REFUSAL_EXIT:
            unrunnable.append(f"{rid} ({r.get('detail')})")
        else:
            broke.append(f"{rid} ({r.get('detail')})")
    when = str(card.get("scored_at") or card.get("banked") or "?")
    if broke:
        return Check("holdout", "FAIL",
                     f"the held-out prediction is BREACHED at the last scoring ({when}): "
                     f"{', '.join(broke)} — the surface the author held out actually broke")
    if unrunnable:
        return Check("holdout", "WARN",
                     f"UNRUNNABLE at the last scoring ({when}) — refused to grade (rc "
                     f"{REFUSAL_EXIT}), a missing dependency or an absent service, never a "
                     f"pass: {', '.join(unrunnable)}")
    if unpaid:
        return Check("holdout", "WARN",
                     f"the wake's wall budget could not pay for {len(unpaid)} check(s) at the "
                     f"last scoring ({when}): {', '.join(unpaid)} — UNPROVEN")
    return Check("holdout", "PASS",
                 f"all {len(passed)} mechanical check(s) held at the last scoring ({when})")


# -------------------------------------------------- (i) fork adjudication (proxy wiring)
def check_fork_adjudication(repo: Path) -> list[Check]:
    """Detect parked forks — live forks (OPEN_STACK 🔴 + corpus_friction `fork` records)
    with no proxy verdict naming them. Consumes THE shared enumeration
    (``fork_adjudicator.enumerate_forks``) that the fork-adjudication DRIVER also consumes:
    one enumeration, two consumers (the up-conjugate law). WARN-tier — the fix is the
    driver (scripts/adjudicate_forks.py), not this reporter."""
    if not (repo / "OPEN_STACK.md").exists():
        return [Check("fork_adjudication", "WARN", "OPEN_STACK.md not found")]
    try:
        src = str(repo / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from laplace.pipeline import fork_adjudicator
        forks = fork_adjudicator.enumerate_forks(repo)
    except Exception as e:  # noqa: BLE001 - the reporter degrades, never hard-fails
        return [Check("fork_adjudication", "WARN",
                      f"could not run the shared fork enumeration: {e}")]
    if not forks:
        return [Check("fork_adjudication", "PASS",
                      "no live forks (OPEN_STACK 🔴 + corpus_friction) — none parked")]
    results: list[Check] = []
    for f in forks:
        if f.referenced:
            results.append(Check("fork_adjudication", "PASS",
                                 f"{f.key}: adjudicated (verdict references it)"))
        else:
            results.append(Check(
                "fork_adjudication", "WARN",
                f"{f.key} [{f.source}]: live fork with no proxy verdict — parked, not "
                "adjudicated (FORK-LAW: decide it or route it GENUINELY-HIS; the driver "
                "is scripts/adjudicate_forks.py)",
            ))
    return results


# ------------------------------------ (i.2) THE STANDING DRAIN (his ruling PV-20260717T002125 item 4)
def check_fork_drain(repo: Path) -> Check:
    """THE STANDING DRAIN — his ruling PV-20260717T002125 item 4 ("proxy cadence: every
    close, automatically"): the close ritual drains parked forks through
    DRAFT → ADVERSARIAL REVIEW → BANK, GENUINELY-HIS excepted, veto retrospective via
    contest records. This beat mirrors tonight's live pass as a close cadence that STOPS
    AT REVIEWED-DRAFTS + names the desk surface; --live is the supervised final step it
    NEVER fires (the BANKING step stays behind the reviewed path — his ruling). WARN tier,
    advisory — NEVER FAIL_ELIGIBLE, NEVER banks (banking a fork automatically would be the
    deferral-by-machine the fork-law forbids in the other direction).

    THE THREE STAGES, as the close walks them:
      1. DRAFT — ``fork_adjudicator.drive(mode="dry-run")`` enumerates the parked forks
         (``enumerate_parked_forks`` already excludes any fork a verdict names, so a
         GENUINELY-HIS-routed fork is decided, not parked — his exception, mechanised),
         hoists the shared frame, and emits the dispatch manifest to a scratch dir with
         ZERO ledger writes.
      2. ADVERSARIAL REVIEW — the manifest is dispatched to a judge; the drafts land on
         THE DESK SURFACE (/desk `forks` lane: OPEN_STACK 🔴 + corpus_friction fork
         records) for the chair. This beat does not perform it (builder ≠ judge; no model
         on the close path); it surfaces that it is owed and where it happens.
      3. BANK — ``scripts/adjudicate_forks.py --live --rulings <reviewed>.json``: the
         supervised final step, run in-session, behind the reviewed path. Named here,
         never fired here.
    PASSes at zero parked forks (the drain is empty)."""
    try:
        src = str(repo / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from laplace.pipeline import fork_adjudicator
        summary = fork_adjudicator.drive(repo, mode="dry-run")
    except Exception as e:  # noqa: BLE001 - advisory; never break the reporter
        return Check("fork_drain", "WARN", f"could not run the standing fork drain (dry-run): {e}")
    n = summary["parked"]
    if n == 0:
        return Check("fork_drain", "PASS",
                     "0 parked forks — the drain is empty (every live fork carries a "
                     "verdict; GENUINELY-HIS routed counts as decided)")
    return Check(
        "fork_drain", "WARN",
        f"{n} parked fork(s) DRAFTED → manifest {summary['manifest_path']} (0 ledger "
        "writes). REVIEW: dispatch the manifest; the drafts land on the /desk forks lane "
        "for the chair. BANK (supervised, behind the reviewed path): "
        "scripts/adjudicate_forks.py --live --rulings <reviewed>.json — the close never "
        "banks (his ruling: banking stays behind the reviewed path)")


# ---------------------------- (i.3) THE FIRST-CHAIR CLAUSE (the infrastructure law)
def _porcelain_paths(repo: Path) -> tuple[Optional[list[str]], str]:
    """The working-tree changed paths (staged + unstaged, added/modified/renamed) from
    ``git status --porcelain``. Returns (paths, note); paths is None when git is
    unavailable so the caller degrades honestly rather than passing on a blind tree."""
    # -uall: list every untracked FILE individually (git otherwise collapses an untracked
    # dir to just "dir/", which would hide a produced artefact banked in a fresh directory).
    rc, out, err = _run(["git", "status", "--porcelain", "-z", "-uall"], repo)
    if rc is None or rc != 0:
        return None, (err.strip() or f"git status rc={rc}")
    paths: list[str] = []
    for rec in out.split("\0"):
        if not rec or len(rec) < 4:
            continue
        p = rec[3:]
        # a rename record is "R  old\0new" — the -z split already separates old/new into
        # two records; each surviving path token is checked on its own, which is fine.
        if " -> " in p:
            p = p.split(" -> ", 1)[1]
        paths.append(p)
    return paths, "working tree"


def _is_produced_artefact(path: str) -> bool:
    low = path.lower()
    if low.endswith(FIRST_CHAIR_ARTEFACT_SUFFIXES):
        return True
    if any(sub in low for sub in FIRST_CHAIR_ARTEFACT_SUBSTRINGS):
        return True
    if _SURFACE_HTML_RE.search(path):
        return True
    return False


def check_first_chair(repo: Path) -> Check:
    """FAIL_ELIGIBLE — THE FIRST-CHAIR CLAUSE (the infrastructure law, ARMING_2026-07-16):
    a working tree carrying a PRODUCED ARTEFACT (a compiled ``.pdf``, a ``minted`` output,
    a rebuilt served ``src/laplace/*.html`` surface) MUST also carry a banked
    ``evidence/FIRST_CHAIR_*.md`` note NEWER than that artefact — the orchestrator's read
    of what actually shipped, non-delegable (his ruling). No fresh note = an artefact
    banked unread = the close FAILs. A tree with no produced artefact PASSes (nothing to
    chair). mtime is the freshness signal: the note is written AFTER the read of the
    produced thing, so a correct close leaves the note newer than the artefact."""
    changed, note = _porcelain_paths(repo)
    if changed is None:
        return Check("first_chair", "WARN", f"git unavailable — first-chair unverifiable: {note}")
    artefacts = [p for p in changed if _is_produced_artefact(p)]
    existing = [(repo / p) for p in artefacts if (repo / p).is_file()]
    if not existing:
        return Check("first_chair", "PASS",
                     "no produced artefact (pdf / minted / surface rebuild) in the working tree")
    newest_art = max(existing, key=lambda p: p.stat().st_mtime)
    art_mtime = newest_art.stat().st_mtime
    shown = ", ".join(sorted(str(p.relative_to(repo)) for p in existing)[:4])
    if len(existing) > 4:
        shown += f" (+{len(existing) - 4} more)"

    notes = sorted((repo / "evidence").glob(_FIRST_CHAIR_GLOB)) if (repo / "evidence").is_dir() else []
    if not notes:
        return Check(
            "first_chair", "FAIL",
            f"{len(existing)} produced artefact(s) in the tree ({shown}) with NO "
            "evidence/FIRST_CHAIR_*.md note — an artefact cannot ship unread (the "
            "orchestrator's first-chair read is non-delegable). Bank one "
            "(evidence/FIRST_CHAIR_2026-07-17_seam5.md is the shape)")
    newest_note = max(notes, key=lambda p: p.stat().st_mtime)
    if newest_note.stat().st_mtime <= art_mtime:
        return Check(
            "first_chair", "FAIL",
            f"{len(existing)} produced artefact(s) ({shown}) NEWER than the latest "
            f"first-chair note ({newest_note.name}) — the note predates the artefact, so "
            "the produced thing was not read after it was produced. Re-read what shipped "
            "and bank a fresh evidence/FIRST_CHAIR_*.md note")
    return Check(
        "first_chair", "PASS",
        f"{len(existing)} produced artefact(s) chaired by {newest_note.name} "
        "(note newer than the artefact)")


# ------------------------------------------ (j) unseal follow-through (raw uncommitted)
def check_unseal_follow_through(repo: Path) -> Check:
    dump = repo / "archive" / "soul_dump"
    if not dump.is_dir():
        return Check("unseal_follow_through", "PASS", "no archive/soul_dump present")
    rc, out, err = _run(
        ["git", "ls-files", "--others", "--exclude-standard", "archive/soul_dump"], repo)
    if rc is None:
        return Check("unseal_follow_through", "WARN", f"git unavailable: {err.strip()}")
    untracked = [ln for ln in out.splitlines() if ln.strip()]
    if not untracked:
        return Check("unseal_follow_through", "PASS", "archive/soul_dump fully tracked")
    return Check(
        "unseal_follow_through", "WARN",
        f"{len(untracked)} untracked file(s) under archive/soul_dump — raw/distillate "
        "present but uncommitted; the unseal verdict says commit it",
    )


# -------------------------------------------------- (k) cold-wake coverage (rehearsal)
def check_cold_wake_coverage(repo: Path) -> Check:
    """WARN-only v1: the rehearsal's mechanical half — the writer of a session's trace must pass
    the reader's test before it's banked. Rebuilds the grade-0 (engine + person, since identity
    rows only resolve through the person payload), grade-1, and grade-2 hello payloads
    in-process and scores each against its own grade's rows in holdout/COLD_WAKE_QUESTIONS.md."""
    try:
        src = str(repo / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from laplace.engine import cold_probe, self_corpus
        questions = repo / "holdout" / "COLD_WAKE_QUESTIONS.md"
        if not questions.exists():
            return Check("cold_wake_coverage", "WARN", "holdout/COLD_WAKE_QUESTIONS.md not found")
        rows = cold_probe.load_questions(questions)
        payloads = [
            self_corpus.reconstruct_self(repo, grade=0),
            self_corpus.reconstruct_self(repo, grade=0, mode="person"),
            self_corpus.reconstruct_self(repo, grade=1),
            self_corpus.reconstruct_self(repo, grade=2),
        ]
        answered: set[str] = set()
        for payload in payloads:
            answered |= set(cold_probe.score_coverage(payload, rows)["answered"])
        residue = sorted(r["id"] for r in rows if r["id"] not in answered)
    except Exception as e:  # noqa: BLE001 - the rehearsal is advisory; never break the reporter
        return Check("cold_wake_coverage", "WARN", f"could not run cold-wake rehearsal: {e}")
    if not residue:
        return Check("cold_wake_coverage", "PASS", f"all {len(rows)} cold-wake question(s) answered")
    return Check("cold_wake_coverage", "WARN", f"residue: {', '.join(residue)}")


# -------------------------------------------------- (l) CLAUDE.md render (trace-artifact freshness)
def check_claude_md_render(repo: Path) -> Check:
    """FAIL_ELIGIBLE: CLAUDE.md is a banked trace-artifact — a hand-edited or stale render is a
    corrupted artifact, not a style nit. Shells out to scripts/render_claude_md.py --check (rc 0 =
    committed CLAUDE.md matches the render byte-for-byte, rc 1 = drift), the same subprocess
    pattern check_seam_liveness/check_rotation use. Degrades to WARN while the renderer lands."""
    script = repo / "scripts" / "render_claude_md.py"
    if not script.exists():
        return Check("claude_md_render", "WARN", "renderer not yet present")
    rc, out, err = _run([sys.executable, str(script), "--check"], repo)
    if rc is None:
        return Check("claude_md_render", "WARN", f"could not run render_claude_md.py: {err.strip()}")
    if rc == 0:
        return Check("claude_md_render", "PASS", "CLAUDE.md matches the render")
    return Check(
        "claude_md_render", "FAIL",
        f"CLAUDE.md drifted from the render (rc={rc}): {(out.strip() or err.strip())[:300]}",
    )


# ------------------------------------------ (l2) OPEN_STACK render (the banner's own claimed gate)
def check_open_stack_render(repo: Path) -> Check:
    """FAIL_ELIGIBLE (WO-20260817-openstack-render-close-gate, the thin-systems audit 2026-08-17) —
    a copy of check_claude_md_render for the sibling render law. OPEN_STACK.md carries a generated
    banner that STATES "Drift fails the close (render_open_stack.py --check)" and, until this check,
    nothing ran it: no close row, no sewup row, no suite row against the real file - and the file
    had already drifted. The narrower defect than WO-20260812-stratum-render-gates: the banner does
    not merely lack a gate, it CLAIMS one. Same subprocess pattern, same degrade-to-WARN while a
    renderer is absent."""
    script = repo / "scripts" / "render_open_stack.py"
    if not script.exists():
        return Check("open_stack_render", "WARN", "renderer not yet present")
    rc, out, err = _run([sys.executable, str(script), "--check"], repo)
    if rc is None:
        return Check("open_stack_render", "WARN", f"could not run render_open_stack.py: {err.strip()}")
    if rc == 0:
        return Check("open_stack_render", "PASS", "OPEN_STACK.md matches the render")
    return Check(
        "open_stack_render", "FAIL",
        f"OPEN_STACK.md drifted from the render (rc={rc}): {(out.strip() or err.strip())[:300]}",
    )


# ------------------------------------------------- (l3) metric currency (the deposit's own verdict)
def check_metric_currency(repo: Path) -> Check:
    """FAIL_ELIGIBLE (WO-20260817-restored-metric-honest-mtime, the thin-systems audit 2026-08-17) —
    the metric-distill gate's DECLINE used to be a print with no promotion path: its one law-bound
    run refused, restored the prior M, and the close banked "the cure shipped ... M is current and
    law-bound". So read the deposit's OWN banked verdict - the last row of .reembed_timing.jsonl,
    which carries ``metric_redistill`` unconditionally - and let it gate the close.

    Verdict space is three, not two (the acceptance-probe schema's first law): a DECLINE or a
    capability failure is a FAIL; "the basis did not move, so there was nothing to re-distill" is a
    genuine PASS (M is current WITH RESPECT TO the standing basis, which is what currency means);
    and no banked row / no verdict at all is UNPROVEN -> WARN, never a silent green. Ruled here
    rather than taken from the row's literal "FAILs when shipped is false", which would have failed
    every basis-unchanged close - the majority of closes - for a state that is not a defect."""
    log = repo / ".reembed_timing.jsonl"
    if not log.is_file():
        return Check("metric_currency", "WARN",
                     "no .reembed_timing.jsonl - the deposit has never banked a metric verdict "
                     "here (UNPROVEN, not green)")
    last = None
    try:
        for line in log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last = json.loads(line)
    except (OSError, ValueError) as exc:
        return Check("metric_currency", "WARN", f"could not read .reembed_timing.jsonl: {exc}")
    if not last or "metric_redistill" not in last:
        return Check("metric_currency", "WARN",
                     "the last banked deposit row carries no metric_redistill verdict (a deposit "
                     "older than the law rider) - UNPROVEN")
    rep = last["metric_redistill"] or {}
    ts = str(last.get("ts", "?"))[:19]
    if rep.get("ran"):
        if rep.get("shipped"):
            return Check("metric_currency", "PASS",
                         f"last deposit ({ts}) re-distilled and SHIPPED M "
                         f"(auc {rep.get('auc_identity')} -> {rep.get('auc_trained')})")
        restored = " - the prior M was restored (bytes + original mtime)" if rep.get(
            "restored_prior_artifact") else ""
        return Check("metric_currency", "FAIL",
                     f"last deposit ({ts}) re-distilled M and the gate DECLINED "
                     f"({rep.get('why')}){restored}: the standing metric is NOT current with the "
                     f"basis this close re-embedded")
    reason = str(rep.get("reason") or rep.get("error") or "no reason banked")
    if "basis unchanged" in reason:
        return Check("metric_currency", "PASS",
                     f"last deposit ({ts}) re-distilled nothing: {reason} - M is current with "
                     f"the standing basis")
    return Check("metric_currency", "FAIL",
                 f"last deposit ({ts}) skipped the metric re-distill: {reason}")


# -------------------------------------------------- (m) graded-close beat gate (W5)
def check_close_beats(repo: Path) -> Check:
    """The GRADED close, as a reading: which Part C beats a sew-up must actually walk,
    derived from the diff since the last banked close (his W5 correction — Part C
    accreted beats and never retired them). Delegates the whole derivation to
    laplace.engine.close_beats; this check only surfaces the plan. Advisory only, NOT
    FAIL_ELIGIBLE: an over- or under-gated beat is a thing to see at close, never a
    mechanical gate on the exit code (the beats themselves still get walked)."""
    try:
        src = str(repo / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from laplace.engine import close_beats
    except Exception as e:  # noqa: BLE001 - the planner is advisory; never break the reporter
        return Check("close_beats", "WARN", f"could not load close_beats: {e}")
    try:
        mark = close_beats.last_banked_close(repo)
        plan = close_beats.beat_plan(repo)
    except Exception as e:  # noqa: BLE001
        return Check("close_beats", "WARN", f"could not derive the beat plan: {e}")
    firing = [b for b in plan if b["fire"]]
    skipped = [b for b in plan if not b["fire"]]
    if mark is None:
        return Check(
            "close_beats", "WARN",
            f"gating unavailable — all {len(plan)} beats fire "
            "(no banked close to diff against)",
        )
    if skipped:
        names = ", ".join(b["beat"] for b in skipped)
        return Check(
            "close_beats", "PASS",
            f"{len(firing)}/{len(plan)} beats fire "
            f"(skipped: {names} — sources unmoved since {mark})",
        )
    return Check(
        "close_beats", "PASS",
        f"{len(firing)}/{len(plan)} beats fire (all sources moved since {mark})",
    )


# -------------------------------------------------- (n) friction-drain report (C5.5)
def check_friction_drain(repo: Path) -> Check:
    """The friction drain's REPORT half, folded into the close as a reading (WARN
    tier, advisory — NOT FAIL_ELIGIBLE). Shells out to scripts/drain_frictions.py
    --report — the ONE producer, run READ-ONLY: the close never runs the drain's
    draft/apply halves (reporter law — draft FIX_PROPOSALS, ratify, apply all stay
    manual). Surfaces open/consumed friction counts plus the residual tally of
    findings that exist SOLELY as raw FEEDBACK appends (never drained through the
    ledger door). WARNs loudly when that tally is nonzero; else PASSes the counts."""
    script = repo / "scripts" / "drain_frictions.py"
    if not script.exists():
        return Check("friction_drain", "WARN", "scripts/drain_frictions.py not found")
    ledger = repo / "corpus_friction" / "laplace_engine.jsonl"
    rc, out, err = _run(
        [sys.executable, str(script), "--report",
         "--ledger", str(ledger), "--root", str(repo)], repo)
    if rc is None:
        return Check("friction_drain", "WARN",
                     f"could not run drain_frictions.py --report: {err.strip()}")
    if rc != 0:
        return Check("friction_drain", "WARN",
                     f"drain_frictions.py --report exited {rc}: {(err or out).strip()[:200]}")
    try:
        rep = json.loads(out)
    except json.JSONDecodeError:
        return Check("friction_drain", "WARN",
                     f"drain report not JSON: {(out or err).strip()[:200]}")
    n_open, n_consumed = rep.get("open", "?"), rep.get("consumed", "?")
    n_raw = rep.get("feedback_raw_append_total", 0)
    base = f"friction ledger: {n_open} open, {n_consumed} consumed"
    if n_raw:
        n_files = len(rep.get("feedback_raw_appends", []))
        return Check(
            "friction_drain", "WARN",
            f"{base}; {n_raw} finding(s) exist SOLELY as raw FEEDBACK appends "
            f"across {n_files} ledger(s) — drain them through the ledger door "
            "(scripts/drain_frictions.py, then ratify FIX_PROPOSALS)",
        )
    return Check("friction_drain", "PASS", f"{base}; no raw-FEEDBACK-only findings")


# -------------------------------------------------- (o) FEEDBACK-append grep-guard (C5.5)
# The grep-guard's ONE sanctioned exception: project-fixedpoint.js's lock tier
# (runLockTier's sealed/referee/vision readers, ~:561/:567/:578) raw-appends each
# finding to the FEEDBACK file BY DESIGN — it is the retained fix_mode=loop
# alternate converge path C5.0 deliberately preserves, while the harnessed
# survivor pours every finding through the ledger door instead. Cited:
# PV-20260713T221204Z-weld-converge-survivor.
_FEEDBACK_APPEND_ALLOW = {"project-fixedpoint.js"}
# a RAW append-to-FEEDBACK call site: the word ``append`` reaching the all-caps
# ``FEEDBACK`` JS const on one line (the agent-prose "append each finding to
# ${FEEDBACK}"). Case-sensitive on FEEDBACK so it never matches the STRUCTURED
# ``append_jsonl(feedback_path, …)`` / ``feedback.jsonl`` pour sites.
_FEEDBACK_APPEND_RE = re.compile(r"append.*\bFEEDBACK\b")


def check_register(repo: Path) -> Check:
    """The register conjugate (advisory, WARN-tier — never FAIL_ELIGIBLE): shells out to
    scripts/audit_register.py, which re-scans the rule-bearing surfaces (STANDING_LAW.md,
    CLAUDE.md, profiles yaml text, src/laplace docstrings, static_shared copy) for the
    register-law tic lexicon and compares each file's total to
    corpus_friction/register_baseline.json. rc 0 = every file at-or-below baseline; rc 1
    = a new tic (a regression) — surfaced as a WARN, never a gate (promotion to FAIL is
    the author's later ruling, the claim_checks precedent)."""
    script = repo / "scripts" / "audit_register.py"
    if not script.exists():
        return Check("register", "WARN", "scripts/audit_register.py not found")
    rc, out, err = _run([sys.executable, str(script)], repo)
    if rc is None:
        return Check("register", "WARN", f"could not run audit_register.py: {err.strip()}")
    tail = out.strip().splitlines()[-1] if out.strip() else f"rc={rc}"
    if rc == 0:
        return Check("register", "PASS", tail)
    return Check("register", "WARN", f"register regression above baseline (advisory): {tail}")


def check_feedback_append_guard(repo: Path) -> Check:
    """FAILS the close (WARN tier per house convention, but the message is LOUD) if
    a raw FEEDBACK-append call site reappears on the HARNESSED pour path — the
    harnessed converge survivor must pour every finding through the ledger door,
    never let one ride the raw FEEDBACK file. Scans .claude/workflows/*.js;
    project-fixedpoint.js is the ONE whitelisted exception (the sanctioned
    fix_mode=loop lock tier — see _FEEDBACK_APPEND_ALLOW). Advisory only (never
    FAIL_ELIGIBLE): a WARN a human must read, not a silent exit-code gate."""
    wf = repo / ".claude" / "workflows"
    if not wf.is_dir():
        return Check("feedback_append_guard", "WARN", ".claude/workflows not found")
    offenders: list[str] = []
    for js in sorted(wf.glob("*.js")):
        if js.name in _FEEDBACK_APPEND_ALLOW:
            continue
        try:
            lines = js.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if _FEEDBACK_APPEND_RE.search(line):
                offenders.append(f"{js.name}:{i}")
    if not offenders:
        return Check(
            "feedback_append_guard", "PASS",
            "no raw FEEDBACK-append on the harnessed pour path "
            "(project-fixedpoint.js's fix_mode=loop lock tier whitelisted)",
        )
    return Check(
        "feedback_append_guard", "WARN",
        "RAW FEEDBACK-APPEND REAPPEARED ON THE HARNESSED POUR PATH — findings "
        "must pour through the ledger door, not ride the raw FEEDBACK file: "
        f"{', '.join(offenders)} (only project-fixedpoint.js's sanctioned "
        "fix_mode=loop lock tier may raw-append)",
    )


# -------------------------------------------------- (p) portable tracked paths (NTFS)
def check_portable_paths(repo: Path) -> Check:
    """FAIL_ELIGIBLE: no tracked path may carry a Windows/NTFS-illegal character
    (: * ? " < > |). One such path aborts a Windows checkout outright — friction
    RW-20260713-203140-001240, where 66 ``sec:...`` files banked with colons
    stranded the author's local pull. A pure ``git ls-files`` scan (no laplace
    import); the sid->path encoder (laplace.pipeline.pathsafe) is the write-side
    twin that keeps such a path from ever banking again. FAILs (not WARNs) — a
    portability break is exactly the trace-corruption class the close must gate."""
    # -z: NUL-delimited RAW paths. Plain ls-files C-quotes any non-ASCII path
    # ("...\342\200\220...") and the surrounding QUOTE characters then match the
    # illegal set — a false positive on NTFS-legal unicode names (hit 2026-07-15:
    # two U+2010 hyphens in archive/soul_dump). The scan must see real bytes.
    rc, out, err = _run(["git", "ls-files", "-z"], repo)
    if rc is None:
        return Check("portable_paths", "WARN", f"git unavailable: {err.strip()}")
    if rc != 0:
        return Check("portable_paths", "WARN", f"git ls-files failed: {err.strip()}")
    illegal = set(NTFS_ILLEGAL_PATH_CHARS)
    offenders = [ln for ln in out.split("\0")
                 if ln.strip() and (set(ln) & illegal)]
    if not offenders:
        return Check("portable_paths", "PASS",
                     "no tracked path carries an NTFS-illegal character")
    shown = ", ".join(offenders[:5]) + (f" (+{len(offenders) - 5} more)"
                                        if len(offenders) > 5 else "")
    return Check(
        "portable_paths", "FAIL",
        f"{len(offenders)} tracked path(s) carry NTFS-illegal char(s) "
        f"[{NTFS_ILLEGAL_PATH_CHARS}] — a Windows checkout aborts: {shown}",
    )


# -------------------------------------------- (q) gitignore forward-law (W6.2 / RULED advisory)
def _gitignore_patterns(text: str) -> list[str]:
    """The active IGNORE pattern lines of a .gitignore body: non-blank, non-comment, and NOT a
    ``!`` negation (a negation un-ignores, it never hides a path, so it can't be a forward-law
    violation)."""
    out: list[str] = []
    for ln in text.splitlines():
        s = ln.strip()
        if s and not s.startswith("#") and not s.startswith("!"):
            out.append(s)
    return out


def _added_gitignore_rules(repo: Path, mark: Optional[str]) -> tuple[Optional[list[str]], str]:
    """Ignore-pattern lines present in the working .gitignore but absent at the mark commit —
    i.e. rules ADDED since the last close (committed or still uncommitted). Returns (added, note);
    added is None when the diff cannot be resolved (no mark, or no .gitignore) so the caller can
    say so honestly rather than flag phantom rules."""
    gi = repo / ".gitignore"
    if not gi.is_file():
        return None, ".gitignore not present"
    current = set(_gitignore_patterns(gi.read_text(encoding="utf-8", errors="replace")))
    if not mark:
        return None, "no banked close to diff against"
    rc_sha, sha_out, _ = _run(["git", "rev-list", "-1", f"--before={mark}", "HEAD"], repo)
    sha = sha_out.strip()
    if rc_sha != 0 or not sha:
        return None, "could not resolve the mark commit"
    rc_show, show_out, _ = _run(["git", "show", f"{sha}:.gitignore"], repo)
    mark_set = set(_gitignore_patterns(show_out)) if rc_show == 0 else set()
    added = sorted(current - mark_set)
    return added, f"vs {sha[:10]}"


def _rule_has_rebuild_lane(pattern: str, repo: Path, gi_model, localstate_text: str) -> bool:
    """A .gitignore rule satisfies the forward law if its hidden files have a REBUILD LANE:
    an env/TeX backstop or a comment-documented regen (surfacing_audit's reconstructability
    taxonomy), OR an ensure_state entry (localstate.json) that names the path. Absent all three,
    the rule hides state with no warm-arrival replacement — the class the law forbids."""
    if gi_model is not None:
        try:
            from surfacing_audit import _ENV_BACKSTOP, _TEX_BACKSTOP
            if _ENV_BACKSTOP.search(pattern) or _TEX_BACKSTOP.search(pattern):
                return True
        except Exception:  # noqa: BLE001
            pass
        for r in getattr(gi_model, "rules", []):
            if r.get("pattern") == pattern and r.get("regenerable"):
                return True
    # an ensure_state manifest entry that names the path (its core filename/dirname)
    core = pattern.strip("/").split("/")[-1]
    if core and core in localstate_text:
        return True
    return False


def check_gitignore_forward_law(repo: Path) -> Check:
    """ADVISORY (WARN-only, never FAIL_ELIGIBLE): flags any .gitignore rule added since the last
    close that has NO rebuild lane — no ensure_state entry and no surfacing_audit backstop class.
    The gitignore-forward-law is RULED (RW-20260713-211452-733024): a file may be gitignored only
    if it is trivially rebuildable remotely, its local absence never induces PSU-class compute,
    and any boot serving path has a warm-arrival replacement. That fork RESERVED the exact
    close-gate SHAPE to the author ("His adjudication on the exact gate shape; the law itself is
    ruled, not open") — so this is the WARN-tier surface that shape, deliberately not a gate."""
    try:
        src = str(repo / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from laplace.engine import close_beats
        mark = close_beats.last_banked_close(repo)
    except Exception as e:  # noqa: BLE001 - advisory; never break the reporter
        return Check("gitignore_forward_law", "WARN", f"could not resolve the mark: {e}")

    added, note = _added_gitignore_rules(repo, mark)
    if added is None:
        return Check("gitignore_forward_law", "PASS", f"skipped — {note}")
    if not added:
        return Check("gitignore_forward_law", "PASS", f"no new .gitignore rules {note}")

    gi_model = None
    try:
        scripts_dir = str(repo / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from surfacing_audit import GitignoreModel
        gi_model = GitignoreModel(repo)
    except Exception:  # noqa: BLE001 - fall back to the localstate/backstop-free check
        gi_model = None
    ls = repo / "localstate.json"
    localstate_text = ls.read_text(encoding="utf-8", errors="replace") if ls.is_file() else ""

    orphaned = [p for p in added
                if not _rule_has_rebuild_lane(p, repo, gi_model, localstate_text)]
    if not orphaned:
        return Check("gitignore_forward_law", "PASS",
                     f"{len(added)} new rule(s) {note}, each with a rebuild lane")
    shown = ", ".join(orphaned[:6]) + (f" (+{len(orphaned) - 6} more)" if len(orphaned) > 6 else "")
    return Check(
        "gitignore_forward_law", "WARN",
        f"{len(orphaned)} newly-ignored path(s) {note} with NO rebuild lane "
        f"(no ensure_state entry / no surfacing_audit backstop): {shown} — the gitignore-"
        "forward-law (RW-20260713-211452-733024) wants a warm-arrival replacement or a "
        "rebuild lane; advisory only, the gate shape is reserved to the author",
    )


# ---------------------------------------------- (q) the contact law (2026-07-21b)
def check_contact_law(repo: Path) -> Check:
    """FAIL_ELIGIBLE — THE CONTACT LAW (STANDING_LAW.md 2026-07-21b, his commission):
    the operating contract and the promise ledger must hold at close. Runs
    tests/test_operating_contract.py: honest reds (xfail) pass; an UNFLIPPED marker
    (strict xpass — behavior landed, contract still claims red), a delivered promise
    without evidence, or any other contract failure FAILs the close. A session may
    end with work owed; it may not end with a ledger that lies about it."""
    suite = repo / "tests" / "test_operating_contract.py"
    if not suite.exists():
        return Check("contact_law", "WARN", "tests/test_operating_contract.py not found")
    rc, out, err = _run([sys.executable, "-m", "pytest", str(suite), "-q", "--no-header"],
                        repo, timeout=300)
    if rc is None:
        return Check("contact_law", "WARN", f"could not run the contract suite: {err.strip()}")
    tail = next((ln.strip() for ln in reversed(out.splitlines()) if ln.strip()), f"rc={rc}")
    if rc == 0:
        return Check("contact_law", "PASS", f"contract holds: {tail}")
    return Check(
        "contact_law", "FAIL",
        f"the operating contract is lying (unflipped red, evidence-free delivered row, "
        f"or broken clause): {tail} — fix the ledger or the marker before the close banks")


# ---------------------------------------------- (r) the reaper: orphan census (liveness law)
def check_orphan_census(repo: Path) -> Check:
    """FAIL_ELIGIBLE — THE REAPER (PRM-20260721-liveness-law): the orphan count cannot
    grow. Runs tests/test_liveness.py, which asserts every route scanner.py serves is
    declared in a surface yaml, listed in contract/tombstones.yaml, or in a named
    allowlist (and the conjugate store twin). A red suite means a route or store was
    built and forgotten — the close FAILs it (build-and-forget, structurally caught).
    A PASS is his 'stop growing the stock' gate; the census file names the standing
    stock for his wire-or-tombstone rulings."""
    suite = repo / "tests" / "test_liveness.py"
    if not suite.exists():
        return Check("orphan_census", "WARN", "tests/test_liveness.py not found (the reaper has not landed)")
    rc, out, err = _run([sys.executable, "-m", "pytest", str(suite), "-q", "--no-header"],
                        repo, timeout=300)
    if rc is None:
        return Check("orphan_census", "WARN", f"could not run the reaper suite: {err.strip()}")
    tail = next((ln.strip() for ln in reversed(out.splitlines()) if ln.strip()), f"rc={rc}")
    if rc == 0:
        return Check("orphan_census", "PASS", f"no orphan routes/stores: {tail}")
    return Check(
        "orphan_census", "FAIL",
        f"an orphan route or store is unaccounted (build-and-forget): {tail} — declare it "
        "in a surface yaml or add a contract/tombstones.yaml row before the close banks")


# ---------------------------------------------- (s) the reaper: scroll-law walk (P10 amended)
def _scroll_walk_browser_available() -> tuple[bool, str]:
    """(available, reason). Playwright must be importable; the actual browser binary is
    resolved by chair_walk_scroll_law.py's own _chrome_path() (platform candidates, PATH,
    then Playwright's bundled chromium), which self-reports REFUSAL_EXIT with a named
    reason if truly nothing resolves. This clause used to ALSO pre-check the module-level
    _SCROLL_WALK_CHROME pin directly — a restriction-era vendored-container path
    (/opt/pw-browsers/...) — and WARN-skip before ever invoking the walk if that exact
    literal was absent. On the permanent box (PV-20260820T104500Z) it always is (chromium
    actually lives under ~/.cache/ms-playwright/, which _chrome_path() already finds), so
    that pre-check silently degraded the scroll_law FAIL_ELIGIBLE gate to WARN every close.
    Removed as dead/wrong duplication of logic the sub-walk already owns correctly."""
    try:
        import importlib.util
        if importlib.util.find_spec("playwright") is None:
            return False, "playwright not installed"
    except Exception as e:  # noqa: BLE001
        return False, f"playwright probe failed: {e}"
    return True, ""


def check_scroll_law(repo: Path) -> Check:
    """FAIL_ELIGIBLE — THE SCROLL LAW (P10 as amended 2026-07-21, his verbatim ruling):
    zero horizontal overflow anywhere; page-level vertical scroll bounded ~1.75x
    viewport. Boots a scanner on an ephemeral port and runs scripts/chair_walk_scroll_
    law.py against it. A breach FAILs the close. If the browser (Playwright / the
    vendored chromium) is absent, or a scanner won't boot, the clause SKIPS WITH A
    NAMED REASON (WARN) — never a silent pass on a box that cannot walk."""
    walk = repo / "scripts" / "chair_walk_scroll_law.py"
    if not walk.exists():
        return Check("scroll_law", "WARN", "scripts/chair_walk_scroll_law.py not found")
    ok, reason = _scroll_walk_browser_available()
    if not ok:
        return Check("scroll_law", "WARN", f"skipped — no browser available ({reason}); "
                     "the scroll-law walk cannot run on this box")
    # boot a scanner on a free ephemeral port (never the reserved 8770/8771)
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    if port in (8770, 8771):
        return Check("scroll_law", "WARN", "skipped — ephemeral port collided with a reserved port")
    import os
    env = dict(os.environ, LAPLACE_NO_NAVIGATOR="1")
    proc = subprocess.Popen(
        [sys.executable, "-m", "laplace.web.scanner", "--port", str(port)],
        cwd=str(repo), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        import http.client
        deadline = time.time() + 25
        booted = False
        while time.time() < deadline and proc.poll() is None:
            try:
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                c.request("GET", "/"); c.getresponse().read(); c.close()
                booted = True
                break
            except Exception:
                time.sleep(0.4)
        if not booted:
            return Check("scroll_law", "WARN",
                         "skipped — scanner would not boot for the scroll-law walk")
        shots = repo / "evidence" / "scroll_law_close_walk"
        # THE STALE-VERDICT FENCE. This clause grades by READING shots/verdict.json after
        # the walk, but the walk (correctly) does not overwrite a banked verdict on a
        # vacuous run — so a walk that refused would leave LAST close's verdict.json in
        # place and this clause would grade PASS off evidence no run produced. Remember
        # what was there before, and refuse to read a file the walk did not just write.
        verdict_before = shots / "verdict.json"
        stale_mtime = verdict_before.stat().st_mtime if verdict_before.exists() else None
        advisory = [r for r in _SCROLL_WALK_ADVISORY_ROUTES.split(",") if r]
        # walk the FULL roster (gated + advisory) so /guide is still driven +
        # screenshotted every close — nothing is hidden; the verdict.json is then
        # classified below so an advisory-only breach never FAILs the exit code.
        full_roster = ",".join([_SCROLL_WALK_GATED_ROUTES] + advisory)
        rc, out, err = _run(
            [sys.executable, str(walk), "--port", str(port),
             "--routes", full_roster, "--projects", _SCROLL_WALK_PROJECTS,
             "--shots", str(shots)], repo, timeout=420)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()
    if rc is None:
        return Check("scroll_law", "WARN", f"could not run the scroll-law walk: {err.strip()}")
    # rc=3 is the walk's REFUSAL: no browser resolved, or its own preconditions absent.
    # It measured nothing, so this clause grades nothing — WARN with the walk's reason,
    # never the FAIL that reading a nonzero rc as "breach" used to produce.
    if rc == REFUSAL_EXIT:
        said = next((ln.strip() for ln in (out + err).splitlines()
                     if "REFUSED" in ln or "SKIPPED" in ln), f"rc={rc}")
        return Check("scroll_law", "WARN",
                     f"skipped — the scroll-law walk REFUSED TO GRADE: {said}")
    verdict_path = shots / "verdict.json"
    fresh = verdict_path.exists() and (
        stale_mtime is None or verdict_path.stat().st_mtime > stale_mtime)
    if verdict_path.exists() and not fresh:
        return Check("scroll_law", "WARN",
                     f"skipped — the walk (rc={rc}) wrote no new verdict; the "
                     f"{verdict_path.name} on disk is a PREVIOUS run's and is not "
                     "this close's evidence (a stale verdict never passes a close)")
    # The walk script FAILs (rc=1) on ANY breach, gated OR advisory. Re-derive the
    # FAIL-eligible verdict from verdict.json: a breach on a GATED surface FAILs the
    # close; a breach on a named ADVISORY surface (another leg's to fix) is reported
    # loudly but never moves the exit code — the register-zero-disarmed idiom per route.
    advisory_set = set(advisory)
    try:
        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
        breaches = verdict.get("breaches", [])
        walked = verdict.get("walked", 0)
    except Exception as e:  # noqa: BLE001 - no parseable verdict: degrade to raw rc, never pass blind
        tail = next((ln.strip() for ln in out.splitlines() if "SCROLL LAW:" in ln),
                    (out.strip().splitlines()[-1] if out.strip() else f"rc={rc}"))
        if rc == 0:
            return Check("scroll_law", "PASS", tail)
        return Check("scroll_law", "FAIL", f"scroll-law breach (P10 amended): {tail} "
                     f"(verdict unparseable: {e}; screenshots in {shots})")
    if walked == 0:
        return Check("scroll_law", "WARN",
                     "skipped — zero pages walked (a vacuous walk never passes)")
    gated_breaches = [b for b in breaches if b.get("route") not in advisory_set]
    advisory_breaches = [b for b in breaches if b.get("route") in advisory_set]
    adv_note = ""
    if advisory_breaches:
        adv_routes = sorted({str(b.get("route")) for b in advisory_breaches})
        worst = max((b.get("ratio", 0) or 0 for b in advisory_breaches
                     if b.get("law") == "vertical"), default=0)
        adv_note = (f" | ADVISORY (owed, NOT gated): {', '.join(adv_routes)} breach(es) "
                    f"P10 ~{worst}x page scroll — another leg's surface to fix (bounded pane "
                    "scroll owed; re-folds into the gate when it lands, see the census §9 "
                    "owed-fix row)")
    if gated_breaches:
        shown = "; ".join(
            f"{b.get('law')} {b.get('route')} [{b.get('project')}]"
            + (f" ~{b.get('ratio')}x" if b.get('law') == 'vertical' else "")
            for b in gated_breaches[:4])
        return Check("scroll_law", "FAIL",
                     f"scroll-law breach on {len(gated_breaches)} gated page-walk(s) (P10 "
                     f"amended): {shown} (screenshots + {verdict_path}){adv_note}")
    return Check("scroll_law", "PASS",
                 f"{walked} page-walks; gated roster bounded within 1.75x viewport, zero "
                 f"horizontal overflow{adv_note or ' (no advisory exclusions breaching)'}")


# ---------------------------------------------- (t) the reaper: register-zero (ARMED)
#: THE REGISTER-ZERO CLAUSE is ARMED (armed=True) as of the W-register sweep
#: (PRM-20260721-register-zero, 2026-07-22). His register-zero law wants audit_register at
#: ZERO tics; the W-register sweep drove the served/rule-bearing surfaces to absolute zero,
#: the per-file baseline store died (empty ``files`` map — no normalized stock), and
#: audit_register now enforces absolute zero (exit nonzero on any tic). The honest
#: placeholder is retired: a red gate here is now a TRUE red, not a lie over an un-swept
#: corpus, so the clause GATES (FAIL-eligible) — any surviving tic FAILs the close.
_REGISTER_ZERO_ARMED = True


def check_register_zero(repo: Path) -> Check:
    """The register-zero clause (PRM-20260721-register-zero), ARMED. Distinct from
    `register` (the baseline conjugate): this one targets ABSOLUTE ZERO tics, the end
    state the register sweep drove to. It runs scripts/audit_register.py and reads the
    corpus-wide tic total. Now that the sweep has landed and the baseline is dead, it is
    FAIL-eligible (armed=True + "register_zero" in FAIL_ELIGIBLE): total=0 PASSes, any tic
    FAILs the close. It disarms again only if the author deliberately reverts the law."""
    script = repo / "scripts" / "audit_register.py"
    if not script.exists():
        state = "ARMED (armed=True)" if _REGISTER_ZERO_ARMED else "disarmed"
        return Check("register_zero", "WARN", f"scripts/audit_register.py not found [{state}]")
    rc, out, err = _run([sys.executable, str(script)], repo)
    arming = ("ARMED (armed=True) — absolute-zero gate, any tic FAILs"
              if _REGISTER_ZERO_ARMED else
              "DISARMED (armed=False) — arms when the W-register sweep lands at zero")
    if rc is None:
        return Check("register_zero", "WARN", f"could not run audit_register.py [{arming}]: {err.strip()}")
    tail = out.strip().splitlines()[-1] if out.strip() else f"rc={rc}"
    # audit_register prints `total=0` only on its OK path (rc 0); on a breach it prints
    # per-file counts with no absolute total. Read total from anywhere in stdout; at-zero
    # is provable only when the OK line reports total=0.
    m = re.search(r"total=(\d+)", out)
    total = m.group(1) if m else None
    at_zero = (rc == 0 and total == "0")
    if at_zero:
        status = "PASS" if _REGISTER_ZERO_ARMED else "WARN"
        return Check("register_zero", status, f"register at ZERO tics [{arming}]: {tail}")
    # not-zero (or unprovable): armed -> FAIL; disarmed -> WARN
    status = "FAIL" if _REGISTER_ZERO_ARMED else "WARN"
    count = f"{total} tic(s)" if total is not None else "a nonzero tic count (breach path)"
    return Check("register_zero", status,
                 f"register not at zero — carries {count} [{arming}]: {tail}")


# ---------------------------------------------- (u) THE AGING TEETH (W-TEETH, PV-20260722T165050Z)
def check_aging_teeth(repo: Path, today: str) -> Check:
    """FAIL_ELIGIBLE — THE AGING TEETH (his verbatim law tonight: loops left open at
    context time fossilize; an aged ask is a destroyed decision; "carried, named" must
    stop being free). Shells out to scripts/ledger_age_audit.py, which walks the
    accumulating ledgers (work_orders / promises / open_stack_forks) and FAILs any OPEN
    row past its class max quiet age (author-gated 3d / machine 14d) that carries no
    dated defer with an owner (the defer_until/deferred_by note idiom). his-direction
    covenant promises are EXEMPT (carried-not-collected per contract/README.md) but named;
    a fork's trigger is its native condition-defer. THE ASK-OR-DECIDE LAW: ask him, decide
    it, or defer it out loud — a silent carry is the defect this gate catches."""
    script = repo / "scripts" / "ledger_age_audit.py"
    if not script.exists():
        return Check("aging_teeth", "WARN", "scripts/ledger_age_audit.py not found")
    rc, out, err = _run([sys.executable, str(script), "--repo", str(repo),
                         "--today", today], repo, timeout=120)
    if rc is None:
        return Check("aging_teeth", "WARN", f"could not run ledger_age_audit.py: {err.strip()}")
    tail = next((ln.strip() for ln in reversed(out.splitlines())
                 if ln.startswith("VERDICT=")), "")
    if rc == 0:
        return Check("aging_teeth", "PASS",
                     tail or "no open ledger row past its gate without a dated defer")
    # a row line is "  FAIL  [class] ID ..." (two spaces after FAIL); the section header
    # "FAILING (n) ..." must NOT match — require the row's double-space prefix.
    fails = [ln.strip()[4:].strip() for ln in out.splitlines()
             if ln.strip().startswith("FAIL  ")]
    named = "; ".join(fails[:6]) + (f" (+{len(fails) - 6} more)" if len(fails) > 6 else "")
    return Check(
        "aging_teeth", "FAIL",
        f"{tail} — the obligation census failed: an open row is past its max quiet age "
        f"or a ledger read is physically incomplete: {named}. Repair any named integrity "
        "wound; for an aged row, ask him, decide it, or append a defer note "
        "({record:defer, target, defer_until, deferred_by} — scripts/ledger_age_audit.py "
        "names every row and residual)")


# ------------------------------------ (u2) THE OBLIGATION PROBE SWEEP (AP-20's second instrument)
def check_obligation_probe_sweep(repo: Path) -> Check:
    """Report-tier, NEVER FAIL_ELIGIBLE (AP-20, the 2026-08-20 full self-audit): the age audit
    right above answers "is this late?" — it cannot answer "is this done?" (measured live: 8
    fossils rode 72 row-days while ledger_age_audit.py read VERDICT=PASS failing=0 throughout,
    because every one sat inside its defer window or had no gate at all). This shells out to
    scripts/obligation_probe_sweep.py --cheap-only (the close-time tier — the full pytest tier
    is a deliberate campaign-boundary run, not a per-close cost, per AP-20's own risk note),
    which runs every work-order/promise row's acceptance probe and reports PASS/FAIL/UNPROVEN
    plus proposed strike-offs. ADVISORY ONLY: a new instrument earns teeth after a few closes,
    not on its first wiring — this never gates the exit code, only surfaces the reading (the
    same posture as effect_meter/seam_liveness). Every proposed strike-off is report-only; it
    goes through the evidence door by hand, never auto-applied."""
    script = repo / "scripts" / "obligation_probe_sweep.py"
    if not script.exists():
        return Check("obligation_probe_sweep", "WARN", "scripts/obligation_probe_sweep.py not found")
    rc, out, err = _run([sys.executable, str(script), "--cheap-only", "--json"], repo, timeout=120)
    if rc is None:
        return Check("obligation_probe_sweep", "WARN",
                     f"could not run obligation_probe_sweep.py: {err.strip()}")
    try:
        report = json.loads(out)
        s = report["summary"]
    except (json.JSONDecodeError, KeyError) as e:
        return Check("obligation_probe_sweep", "WARN",
                     f"obligation_probe_sweep.py produced unparseable output: {e}")
    reading = (f"cheap-tier sweep: pass={s['pass']} fail={s['fail']} unproven={s['unproven']} "
               f"error={s['error']} skipped_tier(pytest)={s['skipped_tier']} — "
               f"{len(s['proposed_strike_offs'])} strike-off candidate(s) "
               f"(evidence door, never auto-applied)")
    if s["tree_left_dirty_for_operator"]:
        return Check("obligation_probe_sweep", "WARN",
                     f"{reading}; LEFT DIRTY outside the sidecar-restore class: "
                     f"{', '.join(s['tree_left_dirty_for_operator'])}")
    if s["fail"] or s["error"]:
        return Check("obligation_probe_sweep", "WARN",
                     f"{reading} — genuinely-open row(s) found by content probe, not by name-"
                     "match (WARN-tier like landing_sweep: surfaced, never gated, on first wiring)")
    return Check("obligation_probe_sweep", "PASS", reading)


# ---------------------------------------------- (v) THE LANDING SWEEP (W-TEETH)
@dataclass
class LandingCandidates:
    """One landing-sweep finding, read by two rows: landing_sweep (the census) and
    fence_rate (the meter). Computed once per close so the git log and the work-order
    ledger are walked once and both rows report the same candidate set.

    ``ids`` are the bare work-order ids; ``rows`` are the same candidates rendered with
    the reason each was flagged; ``mark`` is the last banked close (empty when there is
    none); ``unavailable`` names the reason the sweep could not run (empty when it ran)."""
    ids: list[str]
    rows: list[str]
    mark: str
    unavailable: str


def landing_candidates(repo: Path) -> LandingCandidates:
    """Cross-reference the still-open work-orders against the git log since the last
    banked close: a work-order naming a file a commit since the close touched, or whose
    ``action`` slug appears in a commit subject, may have landed. A name-match is a
    heuristic, so every consumer treats a row here as a candidate, never as proof."""
    try:
        src = str(repo / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from laplace.engine import close_beats
        mark = close_beats.last_banked_close(repo)
    except Exception as e:  # noqa: BLE001 - advisory; never break the reporter
        return LandingCandidates([], [], "", f"could not resolve the last-close mark: {e}")
    if not mark:
        return LandingCandidates([], [], "", "")
    rc, log_out, err = _run(
        ["git", "log", f"--since={mark}", "--name-only", "--pretty=format:%H%x00%s"], repo)
    if rc is None or rc != 0:
        return LandingCandidates([], [], str(mark), f"git log unavailable: {err.strip()}")
    changed_files: set[str] = set()
    subjects: list[str] = []
    for ln in log_out.splitlines():
        if "\x00" in ln:
            subjects.append(ln.split("\x00", 1)[1].lower())
        elif ln.strip():
            changed_files.add(ln.strip())

    try:
        scripts_dir = str(repo / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import ledger_age_audit as _la
        records = _la._read_jsonl(repo / _la.WORK_ORDERS)
        opens = _la._open_work_orders(records)
        notes = _la._defer_notes(records)
    except Exception as e:  # noqa: BLE001
        return LandingCandidates([], [], str(mark),
                                 f"could not read the work-order ledger: {e}")

    ids: list[str] = []
    rendered: list[str] = []
    for r in opens:
        du, _by = _la._live_defer(r, notes, date.today())
        if du:
            continue  # a named, dated defer already accounts for it
        blob = " ".join(str(r.get(k, "")) for k in
                        ("what", "fix", "blocked_by", "action", "corpus"))
        hits = sorted(f for f in changed_files if len(f) > 6 and f in blob)
        action = (r.get("action") or "").strip().lower()
        subj_hit = bool(action) and any(action in s for s in subjects)
        if hits or subj_hit:
            why = []
            if hits:
                why.append("touched " + ", ".join(hits[:2]) + (f" (+{len(hits) - 2})" if len(hits) > 2 else ""))
            if subj_hit:
                why.append(f"action '{action}' named in a commit")
            ids.append(str(r.get("id")))
            rendered.append(f"{r.get('id')} [{'; '.join(why)}]")
    return LandingCandidates(ids, rendered, str(mark), "")


def _named_ids(ids: list[str], cap: int = 5) -> str:
    """The ids themselves, bounded — the row names its numbers rather than only counting
    them. 'none' when the list is empty."""
    if not ids:
        return "none"
    shown = ", ".join(ids[:cap])
    return shown + (f" (+{len(ids) - cap} more)" if len(ids) > cap else "")


def check_landing_sweep(repo: Path, found: Optional[LandingCandidates] = None) -> Check:
    """WARN-tier (never FAIL_ELIGIBLE) — THE LANDING SWEEP: an OPEN work-order whose work
    has actually LANDED but was never resolved through the evidence door (the census's
    "landed-but-open" class — promises reading open with the work merged). WARN, not FAIL,
    deliberately: a name-match is a heuristic (a commit touching a mentioned file does not
    prove the WO's specific work is done), and a FAIL here needs semantics stronger than a
    string coincidence. Resolve a truly-landed WO through storyboard.resolve_work_order
    (the evidence door), or say why it is still open."""
    found = landing_candidates(repo) if found is None else found
    if found.unavailable:
        return Check("landing_sweep", "WARN", found.unavailable)
    if not found.mark:
        return Check("landing_sweep", "PASS", "no banked close to diff against")
    if not found.rows:
        return Check("landing_sweep", "PASS",
                     f"no open work-order names a file/action that landed since {found.mark[:10]}")
    shown = "; ".join(found.rows[:5]) + (f" (+{len(found.rows) - 5} more)" if len(found.rows) > 5 else "")
    return Check(
        "landing_sweep", "WARN",
        f"{len(found.rows)} open work-order(s) name work that MAY have landed since the last "
        f"close (heuristic — a name-match, not proof): {shown}. Resolve a truly-landed one "
        "through the evidence door (storyboard.resolve_work_order) or say why it is still open")


# ------------------------------------------- (v-b) the fence meter (DECISION 2026-08-17)
def check_fence_rate(repo: Path, found: Optional[LandingCandidates] = None) -> Check:
    """WARN-tier (never FAIL_ELIGIBLE) — the fence meter, step 2 of
    DECISION_2026-08-17_fence-promotion-sequencing.md. The landing sweep's candidate ids
    are the denominator; laplace.engine.reconstruction_fence.false_negative_report says which of
    them a banked probe named at the authoring moment (caught) and which the fence stayed
    silent on (missed). The row names the ids on both sides and prints the rate.

    Two things this row will not do. It never banks: false_negative_report is called with
    no stamp, so the close stays a pure reporter and reads no clock. And it never reports
    a rate over an empty denominator — with no landed candidate yet the rate is undefined,
    printed as such, since 0.0 there would read as a perfect score.

    Advisory at this tier by the decision's own sequencing: FAIL waits on the
    store-faithfulness work orders and then arrives per surface, on that surface's
    measured precision. So this row can WARN, and never moves the exit code."""
    found = landing_candidates(repo) if found is None else found
    if found.unavailable:
        return Check("fence_rate", "WARN",
                     f"no landing-sweep candidates to measure against: {found.unavailable}")
    if not found.mark:
        # No mark is NOT "the sweep ran and found nothing": either no close has banked
        # yet, or close_beats.last_banked_close could not run under this interpreter
        # (it collapses both to None - e.g. dulwich absent outside .venv). Name the
        # true state; "no landed candidates yet" here would be a false reason.
        return Check("fence_rate", "PASS",
                     "no banked close mark (none banked yet, or the mark reader could "
                     "not run under this interpreter) - no window to measure, rate "
                     "undefined")
    try:
        src = str(repo / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from laplace.engine import reconstruction_fence
    except Exception as e:  # noqa: BLE001 - advisory; never break the reporter
        return Check("fence_rate", "WARN", f"laplace.engine.reconstruction_fence unimportable: {e}")
    try:
        report = reconstruction_fence.false_negative_report(repo, found.ids)
    except Exception as e:  # noqa: BLE001
        return Check("fence_rate", "WARN", f"could not read the fence probe ledger: {e}")

    rate = report.get("false_negative_rate")
    caught = [str(c.get("id")) for c in (report.get("caught") or [])]
    missed = [str(m) for m in (report.get("missed") or [])]
    banked = report.get("probes_banked", 0)
    tail = (f"{banked} probe(s) banked; advisory tier — the fence promotes per surface "
            "(DECISION_2026-08-17_fence-promotion-sequencing.md)")
    if rate is None:
        return Check("fence_rate", "PASS",
                     f"false-negative rate undefined (no landed candidates yet) — nothing "
                     f"for the fence to have caught since {found.mark[:10] or 'the last close'}; "
                     f"{tail}")
    reading = (f"false-negative rate {rate} ({len(missed)} missed of {len(found.ids)} "
               f"landed candidate(s)) — caught: {_named_ids(caught)}; "
               f"missed: {_named_ids(missed)}; {tail}")
    if not missed:
        return Check("fence_rate", "PASS", reading)
    return Check("fence_rate", "WARN", reading)


def run_all(repo: Path, today: str) -> list[Check]:
    checks: list[Check] = []
    checks.append(check_git_state(repo))
    checks.append(check_portable_paths(repo))
    checks.append(check_gitignore_forward_law(repo))
    checks.append(check_recurrence(repo))
    checks.append(check_durable_refs(repo))
    checks.append(check_claim_checks(repo))
    checks.append(check_supersede_sweep(repo))
    checks.append(check_seam_liveness(repo))
    checks.append(check_effect_meter(repo))
    checks.append(check_rotation(repo))
    checks.append(check_handoff_freshness(repo, today))
    checks.append(check_probe_before_claim(repo))
    checks.append(check_ledger_freshness(repo, today))
    checks.append(check_session_handoff_dated(repo, today))
    checks.append(check_open_stack_sweep(repo, today))
    checks.extend(check_instrument_usage(repo, today))
    checks.append(check_holdout(repo))
    checks.extend(check_fork_adjudication(repo))
    checks.append(check_fork_drain(repo))
    checks.append(check_first_chair(repo))
    checks.append(check_unseal_follow_through(repo))
    checks.append(check_cold_wake_coverage(repo))
    checks.append(check_claude_md_render(repo))
    # the sibling render law (its banner already claims this gate) + the deposit's own
    # metric verdict — the thin-systems audit's two close gates, 2026-08-17.
    checks.append(check_open_stack_render(repo))
    checks.append(check_metric_currency(repo))
    checks.append(check_close_beats(repo))
    checks.append(check_friction_drain(repo))
    checks.append(check_feedback_append_guard(repo))
    checks.append(check_register(repo))
    checks.append(check_contact_law(repo))
    # THE AGING TEETH + THE LANDING SWEEP (W-TEETH, PV-20260722T165050Z): carried-named
    # stops being free — a stale undeferred row FAILs; a landed-but-open WO WARNs.
    checks.append(check_aging_teeth(repo, today))
    # THE OBLIGATION PROBE SWEEP (AP-20, 2026-08-20 full self-audit) — the second, orthogonal
    # instrument beside the age audit: age answers "is this late?", the probe sweep answers
    # "is this done?" Report-tier first (never FAIL_ELIGIBLE); it earns teeth after a few closes.
    checks.append(check_obligation_probe_sweep(repo))
    # one sweep, two readings: the census row (landed-but-open) and the fence meter
    # (of what landed, how much a probe named first — DECISION_2026-08-17, step 2).
    landing = landing_candidates(repo)
    checks.append(check_landing_sweep(repo, landing))
    checks.append(check_fence_rate(repo, landing))
    # THE REAPER (PRM-20260721-liveness-law): the build-and-forget gates.
    checks.append(check_orphan_census(repo))
    checks.append(check_scroll_law(repo))
    checks.append(check_register_zero(repo))
    return checks


def run_fast_fail_eligible(repo: Path, today: str) -> list[Check]:
    """Bounded, read-only close gates; every declared name must produce one verdict."""
    checks = [
        check_handoff_freshness(repo, today),
        check_session_handoff_dated(repo, today),
        check_open_stack_sweep(repo, today),
        check_claude_md_render(repo),
        check_portable_paths(repo),
        check_first_chair(repo),
        check_register_zero(repo),
        check_aging_teeth(repo, today),
        check_open_stack_render(repo),
        check_metric_currency(repo),
        check_holdout(repo),
    ]
    names = {check.name for check in checks}
    assert names == FAST_FAIL_ELIGIBLE, (
        f"fast close-gate roster drifted: missing={sorted(FAST_FAIL_ELIGIBLE - names)} "
        f"extra={sorted(names - FAST_FAIL_ELIGIBLE)}"
    )
    return checks


def _verdict(checks: list[Check]) -> tuple[bool, list[Check], list[Check]]:
    fails = [c for c in checks if c.status == "FAIL"]
    warns = [c for c in checks if c.status == "WARN"]
    stray = [c.name for c in fails if c.name not in FAIL_ELIGIBLE]
    assert not stray, (
        f"check(s) {stray} returned FAIL but aren't in FAIL_ELIGIBLE — "
        "only missing-trace-artifact checks may gate the exit code"
    )
    return not fails, fails, warns


def main(argv: Optional[list[str]] = None) -> int:
    # Windows consoles default to cp1252; check details carry unicode (→, ⟶).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=(
            "The close ritual's mechanical half as one command: an advisory "
            "reporter over git state, recurrence, rotation, trace-artifact "
            "freshness, instrument-usage, and the holdout. Never mutates "
            "anything; never scores retention or touches the soul."
        )
    )
    parser.add_argument("--repo", default=".", help="repo root to check (default: cwd)")
    parser.add_argument(
        "--today", default=None,
        help="override today's date (YYYY-MM-DD); default: real today (for tests)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument(
        "--fast-fail-eligible", action="store_true",
        help="run the bounded FAIL-eligible roster; pytest shards and browser walk stay owned by sewup",
    )
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    today = args.today or date.today().isoformat()

    checks = (run_fast_fail_eligible(repo, today)
              if args.fast_fail_eligible else run_all(repo, today))
    ok, fails, warns = _verdict(checks)

    if args.json:
        print(json.dumps(
            {
                "repo": str(repo),
                "today": today,
                "checks": [asdict(c) for c in checks],
                "ok": ok,
            },
            indent=1,
        ))
    else:
        name_w = max(len(c.name) for c in checks) if checks else 4
        print(f"close_checklist — {repo}  (today={today})")
        print(f"{'CHECK'.ljust(name_w)}  STATUS  DETAIL")
        for c in checks:
            print(f"{c.name.ljust(name_w)}  {c.status:<6}  {c.detail}")

    if ok:
        print(f"VERDICT=PASS warns={len(warns)}")
    else:
        reasons = ",".join(c.name for c in fails)
        print(f"VERDICT=FAIL checks={len(fails)}/{len(checks)} reasons={reasons} warns={len(warns)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
