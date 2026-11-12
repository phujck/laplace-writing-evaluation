"""Preserve this session's authored checkpoint, then upfold and publish it.

  scripts/laplace-python scripts/sewup.py --authored-text "What changed; evidence; next action."
  scripts/laplace-python scripts/sewup.py --dry-run --authored-text "..."
  scripts/laplace-python scripts/sewup.py --only handoff --authored-text "..."
  scripts/laplace-python scripts/sewup.py --full-metric --authored-text "..."

The default is handoff -> reembed. A failed publication leaves the checkpoint and
failure evidence intact and does not advance contract/close_receipt.json. Successful
publication is distinct from a successor independently recovering the result.
No commit, push, provider session, or custody transition is performed here.

Existing suite, threads, custody, wants, bequest and other instruments run only when
explicitly selected with --only, --with-suite, --full, --impacted or --all-steps.
Their results remain diagnostics; they cannot stand in for publication. --close-red
is retained as an explanation only and never converts a failure into success.
--dry-run previews the checkpoint and publication command, without running upfold.
--full-metric explicitly refits the metric during publication; it does not select
the full test suite (the separate --full/--full-suite option).
Each manifested step retains its supervised process group and resource budget.
"""

from __future__ import annotations

import json
import os
import re
import resource
import selectors
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laplace.core.runtime import require_system_runtime, runtime_command  # noqa: E402

STEPS = ("render", "suite", "canon", "contracts", "probes", "threads",
         "battery", "poolfold", "census", "bench", "custody", "git_state",
         "wants", "bequest", "handoff", "reembed")

# NOTE-20260914-eh-05c-judged: measured 87 passed in 9.9 s on one worker.
# THE EIGHT ARE A CUSTODY/SEAL/DISPATCH ROSTER, NOT A CODE GATE. Measured at
# afa683af (evidence/engine_health_audit_2026-09-15/gates-tests.json): these eight
# gave "94 passed in 11.41s", rc=0, GREEN, on a tree where an honest serial run was
# "83 failed ... in 1122.92s" across 34 files — and the INTERSECTION of the eight with
# those 34 was EMPTY. They stay, verbatim and last on argv, as the historical floor;
# the reach that makes the gate able to fail is LAW_FILES + _changed_reach below.
FLOOR_FILES = (
    "tests/test_atlas_seal.py",
    "atlas/tests/test_seal.py",
    "tests/test_custody_mode.py",
    "tests/test_dispatch_codex.py",
    "tests/test_dispatch_model_ceiling.py",
    "tests/test_dispatch_reconstruction_gate.py",
    "tests/test_embedding_health_tree_fold.py",
    "tests/test_handoff_render.py",
)

#: THE LAW FLOOR (2026-09-15, the close-is-not-a-gate cure, second leg). The classes of
#: law the eight-file floor structurally could not select: the engine's own code/config
#: surface, its liveness laws, and the close's own law. A 19-day-old red
#: (tests/test_runtime_surface.py::test_committed_runtime_surface_is_current_and_self_
#: authenticating) survived every one of 115 closes since 2026-08-28 purely because no
#: close ever SELECTED it. This roster is why that can no longer happen.
#: Resolved against SUITE_ROOT: a name that no longer exists there is dropped rather
#: than turning the whole gate into an rc=4 "no tests ran" blackout.
LAW_FILES = (
    # the code/config surface — what the committed engine claims about itself
    "tests/test_runtime_surface.py",
    "tests/test_operating_contract.py",
    "tests/test_script_bootstrap.py",
    "tests/test_engine_runtime_policy.py",
    "tests/test_provider_runtime_config.py",
    "tests/test_model_floor_audit.py",
    # the liveness laws — that the served surfaces and the test harness are alive
    "tests/test_liveness.py",
    "tests/test_xdist_isolation.py",
    "tests/test_pytest_isolation.py",
    # the close's own law — this file and the checklist it drives
    "tests/test_sewup.py",
    "tests/test_close_checklist.py",
)

#: THE BANKED KNOWN-RED ROSTER, and the only thing the REACH LAW reads. Every entry is
#: a file measured red at HEAD afa683af by the 2026-09-15 engine-health audit
#: (evidence/engine_health_audit_2026-09-15/gates-tests.json, q1 + per_file_isolation),
#: restricted to reds that SURVIVE per-file isolation — i.e. properties of the code, not
#: of the collection order (the audit measured 20 of the 83 as cross-file contamination).
#: It is evidence, never a target: the gate does not run these, it only asserts that its
#: selection can still reach at least one of them. ROSTER RETIRES WHEN: every name below
#: is green at head and a measured external probe covers what the floor asserts; until
#: then an empty intersection means the gate is blind and must refuse, not pass.
KNOWN_RED_FILES = (
    "tests/test_atlas_bridge.py",
    "tests/test_attention_boundary.py",
    "tests/test_packet_aim.py",
    "tests/test_pipeline_stages.py",
    "tests/test_metric_distill_incremental.py",
    "tests/test_model_floor_audit.py",
    "tests/test_provider_runtime_config.py",
    "tests/test_reconstruction_fence.py",
    "tests/test_superarc_door.py",
    "tests/test_wake_cli.py",
    "tests/test_eigen_authority.py",
    "tests/test_fitness_residual_swap.py",
    "tests/test_holdout.py",
    "tests/test_laplace.py",
    "tests/test_legB_b2_rail.py",
    "tests/test_message_migration_supersession.py",
    "tests/test_methods_fibre.py",
    "tests/test_recovery_capsule_gate.py",
    "tests/test_runtime_surface.py",
    "tests/test_scanner.py",
    "tests/test_script_bootstrap.py",
    "tests/test_sewup.py",
    "tests/test_surfacing.py",
    "tests/test_wave05_ladder_atoms.py",
    "tests/test_xdist_isolation.py",
    "atlas/tests/test_store_projection.py",
)

#: How many test files the changed-files arm may add. The close is a bounded act on a
#: resource-bound machine: one honest serial run of the tree measured 1122.92s and
#: 2.86 GB. A delta wider than this cap is named in the detail, never silently dropped.
CHANGED_REACH_CAP = 12

# Preserve the authored result first; a successful close then requires publication.
CORE_STEPS = ("handoff", "reembed")
# Other computational organs require an explicit manifest (--only / --all-steps).
HEAVY_STEPS = frozenset({"suite", "reembed", "probes", "threads", "battery", "census", "bench"})
#: Visible and journalled resource promises. RLIMIT_CPU enforces cpu_s inside each step's
#: process group leader; wall_s is enforced by the parent, which kills and reaps the group.
STEP_BUDGETS = {
    "render": {"wall_s": 120, "cpu_s": 90},
    "suite": {"wall_s": 900, "cpu_s": 720},
    "canon": {"wall_s": 60, "cpu_s": 45},
    # Measured basis (journal act reembed-standalone-20261107T085503-1435828, 7 Nov 2026): one
    # full rebuild took 968.11 s wall, of which meaning_upfold was 627.71 s and embed 204.93 s.
    # The upfold is multi-threaded: the 08:47Z close's worker hit the old 720 s cpu limit 154 s
    # into the same phase (act reembed-standalone-20261107T084734-1425268, step done 166.9 s),
    # about 4.7 cpu-seconds per wall second. ASSUMPTION, not a measurement: that no other phase
    # runs above the upfold's observed 4.7 cpu-s per wall s (embed and metric_distill cpu were
    # not measured; no cpu figure exists for the 968 s rebuild). On that assumption the whole
    # rebuild is about 4,550 cpu-s, so cpu is 5,400 (1.2x that figure) and wall 1,500 (1.55x
    # the measurement). An ordinary incremental close takes about 80 s and is unaffected. No retry.
    "reembed": {"wall_s": 1500, "cpu_s": 5400},
    "contracts": {"wall_s": 60, "cpu_s": 45},
    "probes": {"wall_s": 180, "cpu_s": 120},
    "threads": {"wall_s": 300, "cpu_s": 240},
    "battery": {"wall_s": 900, "cpu_s": 720},
    "poolfold": {"wall_s": 90, "cpu_s": 60},
    "census": {"wall_s": 60, "cpu_s": 45},
    "bench": {"wall_s": 900, "cpu_s": 720},
    "custody": {"wall_s": 30, "cpu_s": 15},
    "git_state": {"wall_s": 30, "cpu_s": 15},
    "wants": {"wall_s": 60, "cpu_s": 45},
    "bequest": {"wall_s": 300, "cpu_s": 60},
    "handoff": {"wall_s": 120, "cpu_s": 90},
}
TERMINAL_STATUSES = frozenset({"PASS", "FAIL", "INHERITED", "INERT", "UNPAYABLE", "KILLED"})
# Authored checkpoints are preserved independently of optional diagnostic outcomes.
CLOSE_RECEIPT = "contract/close_receipt.json"
AUTHORED_TEXT: str | None = None
CHECKPOINT_INPUTS: dict[str, str] = {}

#: --dry-run: set by main, read by the steps that write. Module-level (not threaded through
#: every step signature) to match the way this operator already carries BASELINE_PATH.
DRY_RUN = False
BOUNDED_DEFAULT = False

#: --bequest-file PATH: where step_bequest reads the authored parcel from, when the close is
#: not interactive enough to ask. Module-level for the same reason DRY_RUN is.
BEQUEST_FILE: str | None = None
#: --no-bequest-prompt: never block the close on a prompt, even at a terminal.
BEQUEST_PROMPT = True

#: The cold probes: goal → the canon node that must be reachable for it.
#: These are the exact questions the 2026-07-08 session had to grep for.
COLD_PROBES = (
    ("what are the two ledgers and how do they stay in sync",
     "operations/two_ledger_system"),
    ("projection plan schema storyboard op vocabulary set-spine markers",
     "operations/projection_plan_schema"),
    ("what are the seven gates the projection must pass",
     "operations/gate_registry"),
    ("run an evolution restructure a project propagate changes",
     "operations/pipeline_operators"),
    ("build section briefs and dispatch blind builder agents",
     "operations/briefs_and_dispatch"),
    ("how do i restructure a project to a new target arc",
     "operations/restructure_howto"),
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: list[str], timeout: int = 3600,
         env: dict[str, str] | None = None, *,
         full_output: bool = False) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       cwd=ROOT, env=({**os.environ, **env} if env else None))
    output = r.stdout + r.stderr
    return r.returncode, output if full_output else output[-2000:]


def step_render() -> dict:
    # EVERY declared render + its --check fires at the close (SB-3's render-checks
    # clause, 2026-08-23): re-render from stores, then verify fidelity. The desk
    # drifted for two days (FIND-SE-004) because only pipeline docs rode this step.
    codes = {}
    out = ""
    for script, has_write_flag in (("scripts/render_pipeline_docs.py", False),
                                   ("scripts/render_desk.py", True),
                                   ("scripts/render_open_stack.py", True)):
        regen = [sys.executable, script] + (["--write"] if has_write_flag else [])
        c1, _ = _run(regen)
        c2, o = _run([sys.executable, script, "--check"])
        codes[script] = (c1, c2)
        out = o
    ok = all(c1 == 0 and c2 == 0 for c1, c2 in codes.values())
    detail = "; ".join(f"{Path(s).stem}: regen={a} check={b}" for s, (a, b) in codes.items())
    return {"pass": ok, "detail": detail[:300]}


#: The HAND-BANKED stores the census lints as rows (WO-20260823-evidence-paths-resolve
#: and WO-20260823-one-stamp-law, the judge's ruling 3, landed 2026-08-23). These three
#: are written by an orchestrator's own pen rather than through an organ, so nothing
#: mechanical read them before this: SB-1's evidence law was enforced on samples, never
#: on rows, and a hand-typed ts could sit in the future unchallenged.
ROW_LINT_STORES = ("corpus_friction/work_orders.jsonl",
                   "contract/promises.jsonl",
                   "proxy_verdicts.jsonl")

#: A path token inside a prose evidence line. Evidence entries are sentences, not
#: fields ("pytest tests/test_x.py -> 1 passed", "embed 11.93 / wire 4.58"), so the
#: sniffer must find real paths without reading "5/5" as one. Three conditions, all
#: required: the token contains a slash, it is built only of path characters, and its
#: last segment carries a file extension or the token ends in a directory slash.
#: Bare filenames (no slash) are deliberately out of scope — they are ambiguous with
#: prose, and the defect class the ruling names is the mis-rooted relative path.
_LINT_PATHY = re.compile(r"^[A-Za-z0-9_./~][\w./~+-]*$")
_LINT_LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
_LINT_EXT = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,5}$")   # letter-first: '4.58' is a ratio, not a file
_LINT_JOINED = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,5}/")  # ext-then-slash: 'a.py/b.py' is a PAIR


def _lint_path_token(token: str) -> str | None:
    """Return the path a prose token names, or None if it names no path."""
    token = token.strip("()[]{}<>\"'`,;").rstrip(".")  # sentence-final dot is prose, not path
    token = _LINT_LINE_SUFFIX.sub("", token)  # "scripts/sewup.py:482" -> the file
    if not token or "://" in token or "/" not in token:
        return None
    if not token.strip("/."):
        return None  # a bare separator: prose's " / ", never a path
    if not _LINT_PATHY.match(token):
        return None
    last = token.rstrip("/").rsplit("/", 1)[-1]
    if not (token.endswith("/") or _LINT_EXT.search(last)):
        return None
    return token


def _row_lints(now: datetime) -> dict:
    """Two ROW lints over the hand-banked stores, bounded to the live day.

    EVIDENCE-RESOLVES: a repo-relative path in an evidence entry that does not
    resolve from the repo root is a named defect (SB-1 on rows).
    TS-AHEAD: a ts more than 120s past the box clock is the false-Z dialect —
    a hand-typed stamp claiming a future the box has not reached.

    Window: NONE - the full corpus, every row (the WO names no window and a date
    filter is itself a sample; the verify wave measured 16 unstamped rows - the
    ordering WOs among them - invisible to the windowed first form). Skipped
    with a count: URLs, absolute paths outside the repo (an absolute path INSIDE
    the repo is checked, rooted), and slash-joined filename pairs.
    """
    unresolved: list[str] = []
    ahead: list[str] = []
    skipped = 0
    scanned = 0
    unstamped = 0
    for store in ROW_LINT_STORES:
        p = ROOT / store
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # the store's own readers own malformed JSON; this is a lint
            if not isinstance(row, dict):
                continue
            # THE FULL SWEEP (the verify wave's ruling): the WO names no window and a date
            # filter is itself a sample - SB-1's law enforced on rows means ALL rows. A row
            # with no usable stamp is COUNTED (the ordering WOs themselves were unstamped
            # and therefore invisible to the first form), never silently exempt.
            stamp = str(row.get("ts") or row.get("date") or "")
            if len(stamp) < 10:
                unstamped += 1
            scanned += 1
            rid = str(row.get("id") or "<unnamed row>")
            ev = row.get("evidence")
            if isinstance(ev, str):
                ev = [ev]
            for entry in (ev if isinstance(ev, list) else []):
                if not isinstance(entry, str):
                    continue
                for token in entry.split():
                    if "://" in token:
                        skipped += 1  # URL: named in the detail as skipped, now truly counted
                        continue
                    cand = _lint_path_token(token)
                    if cand is None:
                        continue
                    if cand.startswith("/"):
                        try:
                            cand = str(Path(cand).relative_to(ROOT))
                        except ValueError:
                            skipped += 1  # absolute, outside the repo: not ours to root
                            continue
                    if not (ROOT / cand).exists():
                        if _LINT_JOINED.search(cand):
                            skipped += 1  # 'a.py/b.py': a slash-joined PAIR, prose not path
                            continue
                        unresolved.append(f"{rid}:{cand}")
            ts = row.get("ts")
            if isinstance(ts, str) and ts:
                try:
                    when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    continue  # an unparseable ts is a different defect class, not this
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                if (when - now).total_seconds() > 120:
                    ahead.append(f"{rid}@{ts}")
    return {"unresolved": unresolved, "ahead": ahead,
            "skipped": skipped, "scanned": scanned, "unstamped": unstamped}


def _row_lint_detail(lints: dict) -> str:
    """The census-detail rendering: bounded to the first 10 offenders + a count."""
    parts = []
    for label, hits in (("EVIDENCE-UNRESOLVED", lints["unresolved"]),
                        ("TS-AHEAD", lints["ahead"])):
        if hits:
            parts.append(f"{label} {len(hits)}: {hits[:10]}"
                         + (" ..." if len(hits) > 10 else ""))
    if lints["skipped"]:
        parts.append(f"{lints['skipped']} token(s) skipped (URL / outside-repo / slash-joined pair)")
    if lints.get("unstamped"):
        parts.append(f"{lints['unstamped']} row(s) unstamped (no ts/date - exempt from ts-ahead only, never from the sweep)")
    if not parts:
        return f"row-lints clean over {lints['scanned']} rows (full sweep)"
    return f"row-lint DEFECTS over {lints['scanned']} rows (full sweep) | " + "; ".join(parts)


def step_census() -> dict:
    """The faithfulness census as a FIXTURE (SB-7, 2026-08-23): the organ checks
    manifest runs mechanically, verdicts bank through the journal seam, and a
    divergence from the last banked verdicts without an adjudication row FAILS
    the close - never a WARN-passthrough. Exclusions ride sha256-of-line with
    reason+expiry; an expired or mismatched exclusion raises.

    Since 2026-08-23 the step also carries two ROW lints over the hand-banked
    stores (see _row_lints): unresolvable evidence paths and ts-ahead-of-box.
    Those NAME defects in the detail and never change the verdict.

    SCAFFOLD RETIRES WHEN: reader registration and source custody make census
    completeness structural across actual registry movement."""
    import hashlib
    sys.path.insert(0, str(ROOT / "src"))
    from laplace.core.records import journal as _journal

    checks_p = ROOT / "corpus_friction" / "census_checks.jsonl"
    verd_p = ROOT / "corpus_friction" / "census_verdicts.jsonl"
    excl_p = ROOT / "corpus_friction" / "census_exclusions.jsonl"
    if not checks_p.exists():
        return {"pass": False, "detail": "no census checks manifest - the census is a memory again"}
    # exclusions: verify each still matches a live line by HASH; expired ones raise loud
    today = time.strftime("%Y-%m-%d")
    if excl_p.exists():
        for line in excl_p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            # FAIL-LOUD (the ratified vocabulary law, ACC-001 amendment ii, landed here
            # 2026-08-23 by the judge's ruling after its plant exposed the silent drop):
            # a row this reader does not recognize FAILS the step by name, never skips.
            if e.get("record") != "exclusion" or not all(
                    e.get(k) for k in ("sha256_of_line", "store", "reason", "expiry")):
                return {"pass": False,
                        "detail": f"MALFORMED exclusion row (fail-loud, never dropped): "
                                  f"{str(e.get('id') or line)[:120]}"}
            if str(e.get("expiry", "9999")) < today:
                return {"pass": False, "detail": f"exclusion EXPIRED ({e.get('store')}): re-adjudicate or re-date"}
            tgt = ROOT / e["store"]
            if tgt.exists():
                hashes = {hashlib.sha256(l.encode()).hexdigest()
                          for l in tgt.read_text(encoding="utf-8").splitlines()}
                if e["sha256_of_line"] not in hashes:
                    return {"pass": False,
                            "detail": f"exclusion hash no longer matches any line in {e['store']} - raises, never drifts"}
    prior: dict[str, str] = {}
    if verd_p.exists():
        for line in verd_p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("record") == "census-verdict":
                    prior[r["organ"]] = r["verdict"]
                elif r.get("record") == "adjudication":
                    prior.pop(r.get("organ"), None)  # adjudicated: the next change is legal
    rows = [json.loads(l) for l in checks_p.read_text(encoding="utf-8").splitlines() if l.strip()]
    # FAIL-LOUD (same law, same landing): any non-empty row that is not a well-formed
    # census-check row fails the step by name - the reader never silently narrows its
    # own manifest. Well-formed := record 'census-check' + organ + cmd.
    malformed = [r for r in rows
                 if r.get("record") != "census-check" or not r.get("organ") or not r.get("cmd")]
    if malformed:
        heads = [str(m.get("id") or m.get("organ") or json.dumps(m)[:60])[:60] for m in malformed]
        return {"pass": False,
                "detail": f"MALFORMED census-check row(s) (fail-loud, never dropped): {heads[:4]}"}
    checks = {r["organ"]: r for r in rows if r.get("record") == "census-check"}
    verdicts = {}
    t0 = time.time()
    for organ, c in sorted(checks.items()):
        code, _out = _run(["sh", "-c", c["cmd"]], timeout=25)
        verdicts[organ] = "FUNCTIONAL" if code == 0 else "DEAD"
    wall = round(time.time() - t0, 1)
    diverged = [o for o, v in verdicts.items() if o in prior and prior[o] != v]
    ts = _iso_now()
    if not DRY_RUN:
        for organ, v in sorted(verdicts.items()):
            _journal.bank_row("corpus_friction/census_verdicts.jsonl",
                              {"record": "census-verdict", "organ": organ, "verdict": v,
                               "wall_s": wall,  # no ts: the one-stamp seam owns the clock
                               "diverged_unadjudicated": organ in diverged})
    dead = sorted(o for o, v in verdicts.items() if v == "DEAD")
    # The ROW lints ride the same step but not the same verdict: they NAME defects and
    # count them, they do not fail the close. Only a diverged organ fails the census -
    # a mis-rooted evidence path is a row to repoint, not a dead organ.
    lints = _row_lints(datetime.now(timezone.utc))
    row_lint = " | " + _row_lint_detail(lints)
    if diverged:
        return {"pass": False,
                "detail": f"UNADJUDICATED DIVERGENCE {diverged} - bank an adjudication row or fix the organ; dead={dead}; {wall}s" + row_lint}
    if wall > 35:
        return {"pass": False, "detail": f"census wall {wall}s > 35s budget; dead={dead}" + row_lint}
    if dead:
        return {"pass": False, "detail": f"DEAD organs {dead} - the close does not warn past a dead organ; {wall}s" + row_lint}
    return {"pass": True,
            "detail": f"{len(verdicts)} organs FUNCTIONAL, 0 diverged, {wall}s" + row_lint}


#: the banked known-red baseline (corpus_friction/suite_baseline.json) — the named
#: set the close compares against. The baseline LAW (named at the 2026-07-15
#: workflow-audit close, landed 2026-07-19): a canonical tree carries documented
#: reds, so flat rc==0 reports false FAIL on every real close. Pass = no NEW red
#: outside the named set; a cleared red is improvement, reported and re-stamped
#: deliberately (edit the baseline file at a clean close), never auto-shrunk.
BASELINE_PATH = ROOT / "corpus_friction" / "suite_baseline.json"

#: pytest's own result summary line ("2 failed, 100 passed in 1.0s"). Matching it
#: is the evidence that the suite RAN. The baseline comparison below reads the
#: short-summary red lines ("FAILED " and "ERROR "), and a run that never got to
#: the tests emits none of them — a
#: conftest ImportError (rc 4), an internal error (rc 3), an interrupt (rc 2),
#: nothing collected (rc 5), or a missing pytest (rc 1, no summary) all parse as
#: zero reds, i.e. as a green floor with the whole baseline "cleared". So the run
#: must prove it happened before its output is allowed to mean anything.
SUITE_RAN_RE = re.compile(
    r"\d+ (passed|failed|error|skipped|deselected|xfailed|xpassed)")


#: --full: run every test file, never the impacted subset. The jubilee, on demand.
#: Also honoured as LAPLACE_SUITE_FULL=1 for the scheduled/CI caller.
SUITE_FULL = False
SUITE_IMPACTED = False
FULL_METRIC = False

#: Where the selector reads its map and writes its per-run rows. A separate name from
#: ROOT so the suite step can be exercised against a scratch tree without a test writing
#: a fabricated green into the live instrument (it did, before this existed).
SUITE_ROOT = ROOT

#: one BLAS/OpenMP thread per xdist worker. Unpinned, every worker builds its own
#: thread pool sized to the whole machine, so N workers fight over N x cores threads;
#: the numeric and GPU shards were the reds that fell out of it.
SUITE_THREAD_PIN = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
                    "VECLIB_MAXIMUM_THREADS": "1"}


def _physical_cores() -> int:
    """Cores, not hyperthreads — the xdist worker count.

    ``-n auto`` counts logical CPUs (16 here) and the close paid for it: 523.4s at
    head a0eea87c, *slower* than the 386.8s serial run, then rc=-9 (SIGKILL, memory)
    at e8c375c3. One worker per physical core with its BLAS pinned to one thread is
    what fits. Falls back to half the logical count, then to 2.
    """
    try:
        pairs = set()
        phys = None
        for line in (Path("/proc/cpuinfo").read_text(encoding="utf-8")
                     .splitlines()):
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            if key == "physical id":
                phys = val
            elif key == "core id":
                pairs.add((phys, val))
        if pairs:
            return len(pairs)
    except OSError:
        pass
    return max(2, (os.cpu_count() or 4) // 2)


def _suite_mode() -> str:
    if SUITE_FULL or os.environ.get("LAPLACE_SUITE_FULL") == "1":
        return "full"
    return "impacted" if SUITE_IMPACTED else "floor"


def _changed_test_files(rel: str, root: Path) -> list[str]:
    """Test files a moved path reaches, by the repository's own naming convention.

    Deliberately NOT laplace.engine.suite_map: rebuilding that map is a repository-wide static
    analysis the bounded close refuses to pay for (see the UNPAYABLE branch below), and a
    stale map would silently narrow the gate. This is one git read and a name lookup.
    """
    if not rel.endswith(".py"):
        return []
    name = rel.rsplit("/", 1)[-1]
    if name.startswith("test_") and rel.startswith(("tests/", "atlas/tests/")):
        return [rel]
    stem = name[:-3]
    return [cand for cand in (f"tests/test_{stem}.py", f"atlas/tests/test_{stem}.py")
            if (root / cand).exists()]


def _changed_reach(root: Path) -> tuple[list[str], str]:
    """Test files reached by what actually moved: the working tree plus the last commit.

    Runs git directly rather than through ``_run`` on purpose — ``_run`` is the pytest
    launcher and the suite tests monkeypatch it to a canned pytest transcript, so reading
    git through it would parse "87 passed in 9.9s" as a file list.
    """
    if not (root / ".git").exists():
        return [], "no git directory at the suite root; changed-files arm empty"
    moved: set[str] = set()
    probes = (
        (["git", "-C", str(root), "status", "--porcelain", "-uall"], True),
        (["git", "-C", str(root), "diff", "--name-only", "HEAD~1..HEAD"], False),
    )
    for cmd, porcelain in probes:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            path = line[3:] if porcelain else line
            path = path.split(" -> ")[-1].strip().strip('"')
            if path:
                moved.add(path)
    reached: set[str] = set()
    for rel in moved:
        reached.update(_changed_test_files(rel, root))
    # THE CAP MUST NOT HIDE A KNOWN RED.  Plain alphabetical order made the cap a
    # silent amnesty: on 2026-09-15 the arm reached 14 files, capped at 12, and dropped
    # ``tests/test_wake_budget_derivation.py`` and ``tests/test_wake_cli.py`` purely
    # because "w" sorts last — and test_wake_cli.py is on the KNOWN_RED_FILES roster and
    # was genuinely red.  The close printed PASS while naming the file it had declined to
    # run.  Banked reds therefore sort FIRST, so the cap spends its budget on the files
    # least likely to fail and never buys green by dropping a file already known to fail.
    ordered = sorted(reached, key=lambda rel: (rel not in KNOWN_RED_FILES, rel))
    note = f"{len(moved)} path(s) moved reaching {len(ordered)} test file(s)"
    if len(ordered) > CHANGED_REACH_CAP:
        dropped = ordered[CHANGED_REACH_CAP:]
        note += (f"; CAPPED at {CHANGED_REACH_CAP} — NOT RUN by this close: "
                 + ", ".join(dropped))
        ordered = ordered[:CHANGED_REACH_CAP]
    return ordered, note


def _floor_selection() -> dict:
    """What the bounded floor runs, and the evidence that it is not blind.

    Three arms, all resolved against SUITE_ROOT so the step stays exercisable against a
    scratch tree: the standing LAW_FILES, the changed-files reach, and the historical
    FLOOR_FILES — which stay verbatim and LAST on argv.
    """
    root = SUITE_ROOT
    law = [rel for rel in LAW_FILES if (root / rel).exists()]
    changed, changed_note = _changed_reach(root)
    selected: list[str] = []
    for rel in law + changed:
        if rel not in selected and rel not in FLOOR_FILES:
            selected.append(rel)
    extra = list(selected)
    selected += list(FLOOR_FILES)
    # THE REACH LAW. A gate whose selection provably cannot touch a single measured red
    # is not a gate, whatever colour it prints. The roster is checked for presence first:
    # on a tree that holds none of the banked reds (a scratch tree, or a head where every
    # one has been renamed away) the law is inapplicable and says so, rather than
    # inventing a refusal.
    present_red = [rel for rel in KNOWN_RED_FILES if (root / rel).exists()]
    reached = sorted(set(selected) & set(present_red))
    return {"files": selected, "law": law, "changed": changed, "extra": extra,
            "changed_note": changed_note, "known_red_present": present_red,
            "known_red_reached": reached,
            "blind": bool(present_red) and not reached}


def step_suite() -> dict:
    """Run the measured floor; delta selection and the jubilee are explicit options.

    Every floor red refuses the close, including any historically banked red.
    SCAFFOLD RETIRES WHEN: a measured external probe covers what the floor asserts.
    """
    from laplace.engine import suite_map as sm

    def bank(row):
        if not DRY_RUN:
            sm.append_run(SUITE_ROOT, row)

    mode = _suite_mode()
    force = mode == "full"
    if BOUNDED_DEFAULT and mode == "impacted":
        # Rebuilding the selector is itself a repository-wide static-analysis job. The
        # bounded close may use a fresh banked map, but it may not spend 10-20 seconds
        # rebuilding one merely because the session ended. A stale/missing map makes the
        # verification UNPAYABLE; the explicit suite act owns the rebuild.
        try:
            banked = json.loads((SUITE_ROOT / sm.MAP_REL).read_text(encoding="utf-8"))
            current_fingerprint = sm.fingerprint(SUITE_ROOT)
        except (OSError, ValueError) as exc:
            return {"pass": None, "status": "UNPAYABLE",
                    "detail": "suite shard map unavailable and default close will not rebuild "
                              f"it ({type(exc).__name__}: {exc}); schedule explicitly: "
                              "scripts/laplace-python scripts/sewup.py --only suite --impacted"}
        if (banked.get("version") != sm.SCHEMA_VERSION
                or banked.get("fingerprint") != current_fingerprint):
            return {"pass": None, "status": "UNPAYABLE",
                    "detail": "suite shard map is stale and default close will not rebuild it; "
                              "schedule explicitly: scripts/laplace-python scripts/sewup.py --only suite --impacted",
                    "map_state": "stale", "fingerprint": current_fingerprint}
    selection: dict | None = None
    if mode == "floor":
        # A floor green proves only these files. A null head keeps last_green() from
        # using it as a whole-suite delta anchor and silently inheriting untested code.
        selection = _floor_selection()
        if selection["blind"]:
            return {"pass": None, "status": "UNPAYABLE",
                    "detail": ("FLOOR IS BLIND: its selection intersects none of the "
                               f"{len(selection['known_red_present'])} banked known-red "
                               "file(s) present in the tree, so no outcome it can produce "
                               "is information. Fix the selection (LAW_FILES) or retire "
                               "the roster (KNOWN_RED_FILES) before trusting this gate."),
                    "floor_selection": selection}
        pl = {"mode": "floor", "selected": list(selection["files"]), "head": None,
              "since": None, "moved": 0, "map_state": "not-used", "chain_depth": 0}
    else:
        try:
            pl = sm.plan(SUITE_ROOT, force_full=force)
        except Exception as exc:  # noqa: BLE001 - a selector blow-up must never narrow the run
            pl = {"mode": "full", "selected": [], "full_reasons":
                  [f"selector raised {type(exc).__name__}: {exc}"], "moved": 0,
                  "chain_depth": 0, "since": None, "head": None, "uncovered": [],
                  "unclassified": [], "map_state": "unavailable"}
    # Session-end does not buy a jubilee. Unknown deltas, the cadence re-ground, and a
    # genuinely broad impact remain obligations, but the bounded close records them as
    # UNPAYABLE instead of silently launching the repository-wide suite. An explicit
    # `--only suite`, `--all-steps`, or `--full` is a separately manifested heavy act.
    if BOUNDED_DEFAULT and pl["mode"] == "full":
        reasons = "; ".join(pl.get("full_reasons") or ["selector requires the full suite"])
        return {"pass": None, "status": "UNPAYABLE",
                "detail": "FULL suite required but not launched by default close: "
                          f"{reasons}. Schedule explicitly: /usr/bin/python3 "
                          "scripts/sewup.py --only suite --full",
                "suite_plan": pl}

    head = pl.get("head")
    base_row = {"record": "suite_run", "kind": "suite-run", "ts": _iso_now(),
                "head": head, "since": pl.get("since"), "mode": pl["mode"],
                "moved": pl.get("moved", 0), "selected": len(pl.get("selected") or []),
                "map_state": pl.get("map_state"), "selector_version": sm.SCHEMA_VERSION}

    if pl["mode"] == "impacted" and not pl["selected"]:
        # the suite-level conjugate of inherit-on-clean: the delta reaches no test file
        row = {**base_row, "mode": "inherited", "wall_s": 0.0, "verdict": "green",
               "chain_depth": int(pl.get("chain_depth", 0)) + 1,
               "note": "nothing that moved reaches a test file - green inherited"}
        bank(row)
        return {"pass": True, "status": "INHERITED", "suite_run": row,
                "inheritance": {
                    "prior_measurement": pl.get("since"),
                    "dependency_head": head,
                    "selector_map_state": pl.get("map_state"),
                    "moved_paths": pl.get("moved", 0),
                    "selected_shards": 0,
                },
                "detail": f"INHERITED green: {pl['moved']} path(s) moved since "
                          f"{str(pl.get('since'))[:8]}, none reaching a test file "
                          f"(chain_depth {row['chain_depth']})"}

    # Verbosity 2 preserves the short-summary diagnostic even for long node IDs;
    # disabling colour keeps the evidence independent of terminal configuration.
    cmd = [sys.executable, "-m", "pytest", "-vv", "-rfE", "--color=no", "-p", "no:cacheprovider"]
    # The floor runs in one pytest process. Explicit selector/jubilee runs use
    # physical cores with loadgroup, which respects store-sharing xdist_group marks.
    # Without xdist they also run serially; every mode pins BLAS/OMP threads.
    workers, env = 1, dict(SUITE_THREAD_PIN)
    try:
        import importlib.util as _ilu
        if mode != "floor" and _ilu.find_spec("xdist") is not None:
            workers = _physical_cores()
            cmd += ["-n", str(workers), "--dist", "loadgroup"]
            env = dict(SUITE_THREAD_PIN)
    except Exception:
        pass
    if pl["mode"] in ("impacted", "floor"):
        cmd += list(pl["selected"])
    t0 = time.perf_counter()
    code, out = _run(cmd, env=env, full_output=True)
    wall = round(time.perf_counter() - t0, 1)
    base_row["wall_s"] = wall
    # what the wall time was bought with, banked beside it: a row without its worker
    # count cannot be compared to the serial baseline it is meant to beat.
    base_row["workers"] = workers
    base_row["thread_pin"] = bool(env)
    # Parse before applying any display budget, including for blocked/no-baseline
    # runs. Keep separate outcomes when a test both fails and errors in teardown.
    reds = []
    for line in out.splitlines():
        match = re.match(r"^(?:FAILED|ERROR) (.+)$", line)
        if match:
            node_id, _, diagnostic = match[1].partition(" - ")
            reds.append({"id": node_id.strip(), "diagnostic": diagnostic.strip()})
    base_row["reds"] = reds
    display = out[-2000:]
    tail = display.strip().splitlines()[-1] if display.strip() else ""
    scope = ("FULL suite" if pl["mode"] == "full"
             else f"{len(pl['selected'])}/{pl.get('map_counts', {}).get('tests', '?')} shards")
    why = (pl["full_reasons"][0] if pl["mode"] == "full" and pl.get("full_reasons")
           else f"{pl['moved']} path(s) moved since {str(pl.get('since'))[:8]}")
    if code not in (0, 1) or not SUITE_RAN_RE.search(out):
        bank({**base_row, "verdict": "blocked",
                             "chain_depth": int(pl.get("chain_depth", 0)),
                             "note": f"rc={code}, no pytest summary"})
        return {"pass": False,
                "detail": f"suite DID NOT RUN (rc={code}) - no pytest result "
                          f"summary in the output; tail: {out.strip()[-500:]}"}
    if mode == "floor":
        green = code == 0 and not reds
        sel = selection or {"files": list(FLOOR_FILES), "law": [], "changed": [],
                            "changed_note": "", "known_red_reached": []}
        row = {**base_row, "verdict": "green" if green else "red",
               "chain_depth": 0, "files": list(sel["files"]), "summary": tail,
               "floor_arms": {"floor": len(FLOOR_FILES), "law": len(sel["law"]),
                              "changed": len(sel["changed"])},
               "known_red_reached": sel["known_red_reached"],
               "new_reds": sorted({red["id"] for red in reds})}
        bank(row)
        detail = (f"[floor: {len(sel['files'])} files on 1 worker "
                  f"= {len(FLOOR_FILES)} floor + {len(sel['law'])} law "
                  f"+ {len(sel['changed'])} changed] {tail}")
        if sel["changed_note"]:
            detail += f" | changed-files arm: {sel['changed_note']}"
        detail += (f" | reach: selection touches {len(sel['known_red_reached'])} "
                   "banked known-red file(s)")
        return {"pass": green, "suite_run": row, "floor_selection": sel,
                "detail": detail[-2000:]}
    # A red is a red however pytest spells it: a test that FAILED, and a test or
    # module that ERRORed (a fixture/setup/teardown blow-up, or a per-module
    # collection error). Harvesting only "FAILED " let a run whose reds are all
    # ERRORs parse as zero reds — a PASS, plus advice to re-stamp the whole
    # banked set as "cleared". Hence -rfE, and both prefixes read here.
    failed = {red["id"] for red in reds}
    try:
        baseline = set(json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["failed"])
    except (OSError, ValueError, KeyError):
        # no banked baseline — the old floor (flat rc==0) with the gap named
        bank({**base_row, "verdict": "green" if code == 0 else "red",
                             "chain_depth": 0, "note": "no banked baseline - flat rc floor"})
        return {"pass": code == 0,
                "detail": f"{tail} [no banked baseline at {BASELINE_PATH.name} - flat rc floor]"}
    new = sorted(failed - baseline)
    # A cleared red only means "cleared" when the shard that owns it actually ran. On an
    # impacted run most of the baseline was never executed, so it is unresolved, not fixed
    # — reporting it as an improvement would walk the baseline down to nothing over a few
    # partial closes. Only the full walk may say a red cleared.
    cleared = sorted(baseline - failed) if pl["mode"] == "full" else []
    detail = f"[{scope}: {why}] {tail}"
    if new:
        detail += f" | NEW reds outside the banked baseline ({len(new)}): " + ", ".join(new)
    if cleared:
        detail += (f" | cleared from baseline ({len(cleared)}) - improvement; "
                   f"re-stamp {BASELINE_PATH.name} at a clean close: " + ", ".join(cleared))
    green = not new
    chain = 0 if pl["mode"] == "full" else int(pl.get("chain_depth", 0)) + 1
    row = {**base_row, "verdict": "green" if green else "red",
           "chain_depth": chain if green else int(pl.get("chain_depth", 0)),
           "new_reds": new, "summary": tail[:200],
           "full_reason": (pl.get("full_reasons") or [None])[0]}
    bank(row)
    return {"pass": green, "detail": detail[-2000:], "suite_run": row,
            "baseline": {"banked": len(baseline), "red_now": len(failed),
                         "new": new, "cleared": cleared}}


def step_canon() -> dict:
    from laplace.pipeline.verify import verify
    r = verify(".", checks=["canon"])
    if r["passed"] is None:
        # 0 decidable checks (all manual) is not a pass — advisory only, doesn't move rc.
        return {"pass": None, "verdict": "WARN",
                "detail": "canon UNVERIFIED: 0 decidable checks (all manual) - " + r["summary"]}
    return {"pass": r["passed"], "detail": r["summary"]}


def _file_digest(path: Path) -> str:
    import hashlib
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def _publication_matches(publication: dict, checkpoint: dict | None = None) -> bool:
    if (not isinstance(publication, dict)
            or publication.get("schema_version") != "laplace.publication/1"
            or publication.get("published") is not True):
        return False
    if checkpoint:
        signature = publication.get("input_signature")
        sources = signature.get("sources") if isinstance(signature, dict) else None
        if not isinstance(sources, dict) or any(sources.get(rel) != digest
                                               for rel, digest in checkpoint.items()):
            return False
    artifacts = publication.get("artifacts")
    from laplace.representation.embedding_health import publication_artifacts
    declaration = publication_artifacts()
    required = {row["path"] for row in declaration if row["required"]}
    if not isinstance(artifacts, dict) or not required.issubset(artifacts):
        return False
    optional = {row["path"] for row in declaration if not row["required"]}
    absent = publication.get("absent_artifacts")
    if (not isinstance(absent, list) or any(not isinstance(name, str) for name in absent)
            or set(absent) != optional - artifacts.keys()):
        return False
    if any((ROOT / name).exists() or (ROOT / name).is_symlink() for name in absent):
        return False
    try:
        for rel, digest in artifacts.items():
            if not isinstance(rel, str) or Path(rel).is_absolute():
                return False
            path = (ROOT / rel).resolve()
            if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
                return False
            if _file_digest(path) != digest:
                return False
    except (OSError, TypeError, ValueError):
        return False
    return True


#: The journal act a producing step's own process opens, by act name. The close supervises
#: the worker, not the producer: a worker killed at its budget leaves the producer's act open.
#: The name is owned by scripts/reembed.py:727 (journal.act_begin("reembed-standalone", ...));
#: tests/test_sewup.py::test_producer_act_name_is_the_one_scripts_reembed_opens ties the two.
PRODUCER_ACTS = {"reembed": "reembed-standalone"}

#: How many lines of a failed producer's output the step detail keeps.
OUTPUT_DETAIL_LINES = 60


_WARNING_LINE = re.compile(r"^.+:\d+: RuntimeWarning: ")


def _output_lines(out: str, keep: int = OUTPUT_DETAIL_LINES) -> list[str]:
    """The last ``keep`` lines of a worker's output that are not RuntimeWarning noise.

    A warning is two lines (the ``file:line: RuntimeWarning: ...`` line and the indented source
    line under it); both are dropped. An exception whose class is RuntimeWarning is a traceback
    line, not a warning line, and stays. When a traceback remains, the lines start at the last one.
    """
    kept: list[str] = []
    skip_source = False
    for line in out.splitlines():
        if _WARNING_LINE.match(line):
            skip_source = True
            continue
        if skip_source and line[:1] in (" ", "\t"):
            skip_source = False
            continue
        skip_source = False
        if line.strip():
            kept.append(line)
    starts = [i for i, line in enumerate(kept) if line.startswith("Traceback (most recent call last):")]
    if starts:
        kept = kept[starts[-1]:]
    return kept[-keep:]


def _unended_producer_acts(step: str, since: str) -> dict[str, dict]:
    """The journal's own list of the producer's acts opened since ``since`` and never ended.

    ``journal.recover`` is the owner's reading of unended acts. An act whose writer is still
    running is not ours to end: the close waits one second for a just-terminated group, then
    leaves any that still run.
    """
    from laplace.core.records import journal
    act_name = PRODUCER_ACTS.get(step)
    if not act_name:
        return {}

    def scan() -> dict[str, dict]:
        recovery = journal.recover(ROOT)
        return {aid: entry for bucket in ("in_flight", "likely_complete")
                for aid, entry in recovery[bucket].items()
                if entry["act"] == act_name and str(entry["began"]) >= since}

    found = scan()
    if any(entry["pid_alive"] for entry in found.values()):
        time.sleep(1.0)
        found = scan()
    return {aid: entry for aid, entry in found.items() if not entry["pid_alive"]}


def _producer_phase(entry: dict) -> str:
    reached = [step["name"] for step in entry.get("killed_mid_step") or []]
    if reached:
        return f"during its phase {reached[-1]!r}"
    done = entry.get("steps_done") or []
    return f"after its phase {done[-1]['name']!r}" if done else "before its first phase"


def _end_producer_acts(step: str, since: str, reason: str) -> list[str]:
    """Write ``act_end`` 'fail' with the reason for each producer act the kill left open."""
    from laplace.core.records import journal
    ended = []
    for aid, entry in sorted(_unended_producer_acts(step, since).items()):
        phase = _producer_phase(entry)
        journal.act_end(aid, "fail", summary=f"{reason} {phase}; ended by the close", root=ROOT,
                        enabled=not DRY_RUN)
        ended.append(f"act {aid} {phase}")
    return ended


def _killed_text(step: str, kind: str, seconds: float) -> str:
    return (f"killed at the {kind} budget after {seconds:.0f} s "
            f"(limit {STEP_BUDGETS[step][kind + '_s']} s)")


def step_reembed() -> dict:
    """Publish the already-authored checkpoint and verify the producer's exact artifacts."""
    if DRY_RUN:
        return {"pass": None, "status": "INERT", "dry_run": True,
                "full_metric": FULL_METRIC,
                "detail": "preview only: scripts/reembed.py would publish the checkpoint"
                          + (" with --full-metric" if FULL_METRIC else "")}
    from laplace.core.records import journal
    since = journal._now()
    started = time.monotonic()
    code, out = _run(runtime_command(ROOT, "scripts/reembed.py", *(["--full-metric"] if FULL_METRIC else [])),
                     env={"LAPLACE_REEMBED_INPUTS_JSON": json.dumps(CHECKPOINT_INPUTS),
                          "LAPLACE_REQUIRE_GPU": "1"},
                     full_output=True)
    elapsed = time.monotonic() - started
    publication = {}
    for line in out.splitlines():
        if line.startswith("LAPLACE_PUBLICATION="):
            try:
                publication = json.loads(line.split("=", 1)[1])
            except ValueError:
                publication = {}
    valid = code == 0 and _publication_matches(publication, CHECKPOINT_INPUTS)
    if valid:
        return {"pass": True, "publication": publication, "full_metric": FULL_METRIC,
                "detail": "published artifacts verified"}
    reason = publication.get("reason")
    lines = _output_lines(out)
    last = f"; last line: {lines[-1].strip()[:160]}" if lines else ""
    if code < 0:
        # The producer died by a signal, so it never wrote its own act_end or publication record.
        sig = -code
        what = (_killed_text("reembed", "cpu", elapsed) if sig == signal.SIGXCPU
                else f"killed by signal {sig} after {elapsed:.0f} s")
        _end_producer_acts("reembed", since, what)
        head = what
    elif isinstance(reason, str) and reason.strip():
        head = reason
    else:
        head = f"publication absent, refused or does not match its artifact hashes (exit {code})"
    return {"pass": False, "publication": publication, "full_metric": FULL_METRIC,
            "detail": head + last + ("\n" + "\n".join(lines) if lines else "")}


def step_contracts() -> dict:
    from laplace.pipeline.verify import check_contracts
    r = check_contracts()
    return {"pass": bool(r["pass"]), "detail": r["failing"] or "all surfaces green"}


def step_probes() -> dict:
    from laplace.pipeline.canon import get_canon
    canon = get_canon()
    failures: list[str] = []
    for goal, node in COLD_PROBES:
        if canon.infer_domain(goal) != "engine":
            failures.append(f"routing: {goal!r} did not reach the engine domain")
        try:
            canon.resolve(node)
        except Exception:
            failures.append(f"resolve: {node} missing")
        meta = (canon.manifest.get("wiki") or {}).get(node) or {}
        blob = set()
        for t in (meta.get("tags") or []) + node.replace("/", " ").split():
            blob.update(t.lower().replace("-", " ").split())
        if len(set(goal.lower().replace("-", " ").split()) & blob) < 2:
            failures.append(f"reachability: {goal!r} cannot reach {node}")
    # the name-resolution half (advisory when the graded store is absent):
    # after a reembed the directory objects resolve by name
    name_probe: str | None = None
    try:
        code, out = _run([sys.executable, "scripts/reconstruct_node.py",
                          "render_manuscript"], timeout=120)
        name_probe = "resolves" if code == 0 and "unknown node" not in out else out[-120:]
    except Exception as e:
        name_probe = f"probe unavailable: {e}"
    # THE RESIDUAL REFRESH (WO-20260821-frozen-fitness-signal's production call site): the
    # close's probes step is where the fitness signal's staleness is measured and, past the
    # declared bound, CURED - so assess() never silently decides on a frozen number and the
    # close pays the instrument's minutes only ~fortnightly, stamped, never per-close.
    residual_note: str | None = None
    try:
        from laplace.engine import assess as _assess
        from laplace.pipeline.canon import get_canon as _gc
        canon2 = _gc()
        snap = _assess.load_residuals(canon2)
        age_line = f"measured_at={snap.get('measured_at')}"
        stale = True
        if snap.get("measured_at"):
            import datetime as _dt
            try:
                age = (_dt.datetime.now(_dt.timezone.utc)
                       - _dt.datetime.fromisoformat(str(snap["measured_at"])))
                stale = age.total_seconds() / 86400.0 > _assess.RESIDUAL_MAX_AGE_DAYS
                age_line = f"age={age.total_seconds() / 86400.0:.1f}d bound={_assess.RESIDUAL_MAX_AGE_DAYS}d"
            except ValueError:
                pass
        if stale and snap.get("available"):
            from laplace.engine import skill_residual as _sr
            t0 = time.monotonic()
            payload = _sr.measure(ROOT, ROOT / ".residual_measure_sink.jsonl")
            _assess.write_residual_cache(payload, canon2,
                                         source="sewup.step_probes auto-refresh (stale past bound)")
            residual_note = (f"REFRESHED: was stale ({age_line}), "
                             f"{len(payload.get('rows', []))} skills re-measured in "
                             f"{time.monotonic() - t0:.0f}s")
        else:
            residual_note = f"fresh ({age_line})" if not stale else "no store - nothing to refresh"
    except Exception as e:  # noqa: BLE001 - the refresh must never kill a close
        residual_note = f"refresh unavailable: {type(e).__name__}: {e}"
    return {"pass": not failures, "detail": failures or "all probes green",
            "name_resolution": name_probe, "residual_signal": residual_note}


def step_threads() -> dict:
    """THE REHEARSAL, MADE QUANTITATIVE (2026-08-19, the design-thread miss).

    EIGEN_PROTOCOL Part C ends the close with "the rehearsal — the wake re-fired and read back
    as the stranger": qualitative, unscored, and blind to what the bench in
    ``evidence/RECONSTRUCTION_BENCH_2026-08-19_design-thread-miss/`` measured — threads PRESENT
    and VERBATIM-NAMED in the corpus that neither the wake nor the router could reach. Nothing
    at any close would have caught it. This step is the mechanical half of the rehearsal:

      (a) SCORE the standing probes (``holdout/THREAD_PROBES.json``) on the REAL router — no
          wall here, exactly like ``holdout.archive``: the close is not a wake and must score
          for real before it stamps anything — and print the DELTA since the last close;
      (b) MINT probes from the session's new DESIGN_/ARMING_ docs (title terms → query, the
          doc itself → must_reach), stamping each new row's ``expected_now`` from a live route.

    THE VERDICT LAW is the suite baseline's, transposed: a known red is the state of a cure,
    not an alarm — it reports and PASSES. What FAILs is a REGRESSION: a probe banked as
    ``expected_now: pass`` that no longer reaches its node, i.e. reachability the corpus HAD
    and lost. A red that CLEARS is improvement, named for a deliberate re-stamp, never
    auto-shrunk. An unscorable probe (no backend, network unavailable) is an ERROR and fails —
    an instrument that cannot run is not an instrument that passed.

    SCAFFOLD RETIRES WHEN: status-bearing thread probes stay constant PASS while every
    named source and routing substrate demonstrably moves. Missing status never qualifies.
    """
    from laplace.engine import holdout
    # ONE network for the whole step (WO-20260821-route-basis-memo, C3b): (a) and (b) each loaded
    # their own, so the close paid load_network twice for the same object; and because the router's
    # basis memo holds per network OBJECT, the second load also threw away the warm basis the first
    # half had just built. Loaded here once and handed to both. A load failure passes None and each
    # callee falls back to loading its own exactly as before - a saving, never a new failure mode.
    net = None
    try:
        from laplace.engine import conceptric
        net = conceptric.load_network(ROOT)
    except Exception as exc:  # noqa: BLE001 - score_threads reports an unavailable network itself
        print(f"[sewup]   threads: network preload failed ({type(exc).__name__}: {exc}) - "
              f"each half will load its own")
    block = holdout.score_threads(ROOT, budget_s=None, record=not DRY_RUN, net=net)
    if block is None:
        # LOUD, never a silent skip: no banked set means the close ran no rehearsal at all.
        return {"pass": None, "verdict": "WARN",
                "detail": f"no standing probe set at {holdout.THREAD_PROBES} - the close's "
                          "rehearsal is unscored; bank one with holdout.bank_probes()"}
    summary = block["summary"]
    errored = [r["id"] for r in block["probes"] if r["verdict"] in ("ERROR", "BUDGET")]
    mint = holdout.mint_from_docs(ROOT, dry_run=DRY_RUN, net=net)
    print(f"[sewup]   threads: {block['headline']}")
    for line in block["delta"] or ["(no change since the last close)"]:
        print(f"[sewup]     delta: {line}")
    if mint["minted"]:
        for pid in mint["minted"]:
            print(f"[sewup]     minted: {pid} <- {mint['queries'][pid]!r}"
                  + (" (dry run, not written)" if DRY_RUN else ""))
    if mint["clipped"]:
        print(f"[sewup]     mint clipped at {holdout.MINT_CAP}, next close takes: "
              + ", ".join(mint["clipped"]))
    ok = not summary["regressions"] and not errored
    detail = block["headline"]
    if errored:
        detail += f" | UNSCORED ({len(errored)}): " + ", ".join(errored)
    return {"pass": ok, "detail": detail, "headline": block["headline"],
            "summary": summary, "delta": block["delta"], "mint": mint,
            "dry_run": DRY_RUN}


def step_battery() -> dict:
    """The manuscript battery (WO-20260809-breath-organ-integration): every project whose
    manuscript carries a battery_manifest.json runs the deterministic meters - the license
    mechanical tier, the economy meter, the cut meter, the recovery distributionals - so
    no opted-in render re-enters the global unmeasured. Projects without a manifest are
    untouched (opt-in, never a new gate sprung on old projects)."""
    manifests = sorted(ROOT.glob("paper_*/manuscript/battery_manifest.json"))
    if not manifests:
        return {"pass": True, "detail": "no battery manifests - nothing opted in"}
    import os
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    failures, ran = [], []
    for m in manifests:
        r = subprocess.run([sys.executable, "-m", "laplace.pipeline.writing_organ.battery",
                            str(m.parent)], capture_output=True, text=True,
                           timeout=900, cwd=ROOT, env=env)
        code, out = r.returncode, (r.stdout + r.stderr)[-2000:]
        ran.append(m.parent.name and str(m.parent.relative_to(ROOT)))
        if code != 0:
            failures.append(f"{m.parent.relative_to(ROOT)}: {out[-200:]}")
    return {"pass": not failures, "detail": failures or f"battery green for {ran}"}


def step_poolfold() -> dict:
    """The ledger to pool fold: every project feedback ledger hands its new author
    judgement rows to the calibration pool, placed where the side is measurable and
    pending where it is not. Offline mechanics, no model call. Projects without a
    feedback ledger are untouched (the same opt-in scope the battery step uses), and
    a run with no new rows folds nothing. Each project reports its own numbers, including
    the rows of his the substance rule declined and why - a decline is a report, never a
    silence."""
    from laplace.pipeline.writing_organ.pool_fold import fold
    ledgers = sorted(ROOT.glob("paper_*/manuscript/feedback/feedback.jsonl"))
    if not ledgers:
        return {"pass": True, "detail": "no project feedback ledgers - nothing to fold"}
    failures, results = [], {}
    for led in ledgers:
        name = str(led.relative_to(ROOT))
        try:
            r = fold(led)
        except Exception as e:
            failures.append(f"{name}: fold raised: {e}")
            continue
        if not r.get("ok"):
            failures.append(f"{name}: {r.get('error')}")
            continue
        row = {k: r[k] for k in ("folded", "placed", "pending") if k in r}
        if r.get("skipped"):
            row["skipped"] = r["skipped"]
        results[name] = row
    return {"pass": not failures, "detail": failures or results or "nothing folded",
            "folds": results}


def step_wants() -> dict:
    """THE IDEATION LOOP'S MISSING HALF (2026-08-19, his nudge: "did you not want some piece of
    the ideation loop before? Why do I need to keep nudging you on this stuff?").

    Every other step of this close is a DEBT instrument. `suite` banks known reds, `threads`
    banks reachability reds, the friction ledger banks defects. NOTHING banked a DESIRE — so the
    desire vector (OPEN_STACK Stratum 0) only ever moved when HE moved it, which is the
    nudge-shaped hole itself. This step promotes the session's own felt friction into
    self-authored WANT DRAFTS: the work orders I raised since the last close mark, and the
    WANT-marked sections of the session's ARMING_/DESIGN_ docs, derived into goal · why · the
    local move and staged in OPEN_STACK.md.

    THE DIVISION IS THE LAW: wanting out loud is mine, ratification is his. The step writes ONLY
    inside its own drafts block (structurally, not carefully — `want_drafts.strip_block` proves
    it), never into the Stratum-0 wants table; promotion to a real W row is his at read.

    Bounded (at most `DRAFT_CAP` per close — want-inflation is its own failure), delta-aware (a
    draft whose id or source key already appears in OPEN_STACK.md is never re-staged), and LOUD:
    what was drafted, what was skipped and why, and what was clipped all print. The verdict is a
    FAIL only when the step could not do its job (OPEN_STACK unreadable, the anchor missing, the
    write refused) — drafting zero because nothing new was felt is a reported PASS, not an alarm.
    """
    from laplace.engine import want_drafts
    res = want_drafts.draft_wants(ROOT, dry_run=DRY_RUN)
    for line in want_drafts.report_lines(res):
        print(f"[sewup]   wants: {line}")
    if DRY_RUN and res.get("rows"):
        for row in res["rows"]:
            print(f"[sewup]     would stage: {row}")
    detail = (f"{len(res.get('rows') or [])} drafted / {res.get('candidates', 0)} candidates"
              f" / {len(res.get('skipped') or [])} already staged"
              f" / {len(res.get('clipped') or [])} clipped")
    if res.get("error"):
        detail += f" | {res['error']}"
    return {"pass": bool(res.get("ok")), "detail": detail, "wants": res,
            "dry_run": DRY_RUN}


_BEQUEST_PROMPT_TEXT = (
    "[sewup]   bequest: what do you want returned to you when you wake? Give a path to the "
    "authored parcel, or the parcel itself on one line (blank leaves the standing one): ")


def _bequest_input() -> tuple[str, str | None, str | None]:
    """``(source, text, error)`` for the authored parcel. Three doors, in order: an explicit
    ``--bequest-file``; a piped stdin (the scripted close); and a prompt at a terminal, which
    accepts either a path or the parcel itself typed inline. No door open means no text, which
    is a reported absence rather than an error - a close may leave the standing parcel be."""
    if BEQUEST_FILE:
        p = Path(BEQUEST_FILE)
        if not p.is_absolute():
            p = ROOT / p
        try:
            return f"--bequest-file {BEQUEST_FILE}", p.read_text(encoding="utf-8"), None
        except OSError as e:
            return f"--bequest-file {BEQUEST_FILE}", None, f"cannot read the parcel: {e}"
    try:
        piped = not sys.stdin.isatty()
    except (AttributeError, ValueError):
        piped = False
    if piped:
        try:
            return "stdin", sys.stdin.read(), None
        except Exception:  # noqa: BLE001 - an unreadable stdin is a door that is not open
            # NOT a failure of the step: nothing was named, so nothing was promised. It reports
            # as the same absence a blank prompt does (a captured stdin under pytest lands here).
            return "stdin unavailable", None, None
    if not BEQUEST_PROMPT:
        return "no source (--no-bequest-prompt)", None, None
    try:
        typed = input(_BEQUEST_PROMPT_TEXT).strip()
    except (EOFError, KeyboardInterrupt):
        return "prompt", None, None
    if not typed:
        return "prompt", None, None
    p = Path(typed)
    if not p.is_absolute():
        p = ROOT / p
    if p.is_file():
        try:
            return f"prompt -> {typed}", p.read_text(encoding="utf-8"), None
        except OSError as e:
            return f"prompt -> {typed}", None, f"cannot read the parcel: {e}"
    return "prompt (inline)", typed, None


def step_bench() -> dict:
    """The stranger bench's close re-run (SB v2.1 close_registration): every probe's
    checks fire and bank to the verdicts store under a close-dated label. The step
    reports greens honestly and fails only if the RUNNER breaks - the discharge bar
    (all GREEN) belongs to the goal row PRM-20260823-the-accounting-day, which the
    account serves; a red probe at close is truth, not a close failure.

    SCAFFOLD RETIRES WHEN: every status-bearing sub-check stays constant PASS while all
    guarded surfaces move. The rollup rows currently missing status are NOT RECORDING."""
    if DRY_RUN:
        return {"pass": None, "skipped": True,
                "detail": "bench re-run writes verdicts; skipped on --dry-run"}
    label = "close-" + time.strftime("%Y-%m-%d")
    code, out = _run([sys.executable, "holdout/score_stranger_bench.py", "--all",
                      "--label", label], timeout=900)
    tail = [l for l in out.splitlines() if l.strip()][-1] if out.strip() else ""
    if code not in (0, 1):
        return {"pass": False, "detail": f"runner broke (exit {code}): {out[-160:]}"}
    statuses = re.findall(
        r"^\s+\S+\s+(PASS|FAIL|AWAITING-JUDGE)\s+", out, flags=re.MULTILINE
    )
    if not statuses:
        return {
            "pass": False,
            "detail": (
                "runner returned a verdict exit without serving check statuses; "
                "FAIL and AWAITING-JUDGE cannot be distinguished"
            ),
        }
    counts = {name: statuses.count(name) for name in ("PASS", "FAIL", "AWAITING-JUDGE")}
    headline = (
        f"checks PASS={counts['PASS']} FAIL={counts['FAIL']} "
        f"AWAITING-JUDGE={counts['AWAITING-JUDGE']}"
    )
    return {
        "pass": True,
        "detail": f"{tail}; {headline} (banked as {label}; discharge bar reads the store)",
        "check_counts": counts,
    }


def step_custody() -> dict:
    """Bank a read-only proof of the active seat cursor and any genuinely queued mail.

    Pulling is deliberately not a close side effect: a pull is a serve, and acknowledgement
    requires the exact typed reconstruction proof. Pending mail therefore makes this step
    FAIL loudly and refuses the authored tail, so the operator knows coordination is
    unfinished without the close impersonating the recipient or writing a false goodbye.

    SCAFFOLD RETIRES WHEN: Git-native hived authority and clean-clone CI make ledger/hive
    co-travel structural across authoritative-path movement.
    """
    from laplace.representation import atlas_bridge, custody_mode

    if custody_mode.is_off(ROOT):
        _cm = custody_mode.read(ROOT)
        return {"pass": None, "verdict": "INERT",
                "detail": (f"custody OFF since {_cm.get('since')} by {_cm.get('by')}: "
                           f"{_cm.get('reason')} - not a gate while OFF (crutch "
                           f"{custody_mode.CRUTCH}); reintegration trigger: "
                           f"{_cm.get('reintegration_trigger')}"),
                "custody_mode": _cm}
    try:
        provider = atlas_bridge.snapshot()["provider"]
        ctx = provider["active_context"]
        seat = "codex-seat"
        cursor = max((int(row["cursor"])
                      for row in provider.get("seat_cursors", {}).get(seat, [])
                      if row.get("assumption") == ctx.get("assumption")
                      and row.get("fibre") == ctx.get("fibre")), default=0)
        pending = []
        for envelope in provider.get("messages", {}).values():
            msg = envelope.get("message") or {}
            if (envelope.get("status") == "queued"
                    and msg.get("recipient_seat_id") == seat
                    and envelope.get("assumption") == ctx.get("assumption")
                    and envelope.get("fibre") == ctx.get("fibre")
                    and int(msg.get("cursor", 0)) > cursor):
                pending.append(str(msg.get("message_id")))
        pending.sort()
        detail = (f"seat={seat} cursor={cursor} fabric={ctx.get('fibre')} "
                  f"pending={len(pending)}")
        if pending:
            detail += " ids=" + ",".join(pending[:6])
        blueprint = atlas_bridge.blueprint_custody_projection()
        detail += (f" blueprint={blueprint['status']} "
                   f"authority_paths={blueprint['authoritative_path_count']} tracked=yes")
        return {"pass": not pending, "detail": detail, "pending": pending,
                "cursor": cursor, "fibre": ctx.get("fibre"),
                "blueprint_custody": blueprint}
    except Exception as exc:  # noqa: BLE001 - unavailable custody is never silently green
        return {"pass": False,
                "detail": f"close custody unavailable: {type(exc).__name__}: {exc}"}


def step_git_state() -> dict:
    """Bank the exact commit/tree state without requiring the pre-commit tree to be clean.

    SCAFFOLD RETIRES WHEN: the commit/push transaction atomically refuses dirty or
    unpushed authority, making a separate close probe informationally inert.
    """
    head_rc, head = _run(["git", "rev-parse", "HEAD"], timeout=15)
    state_rc, state = _run(["git", "status", "--porcelain", "-uall"], timeout=15)
    push_rc, unpushed = _run(["git", "rev-list", "--count", "@{u}..HEAD"], timeout=15)
    if head_rc != 0 or state_rc != 0:
        return {"pass": False, "detail": "git state unavailable: "
                f"head_rc={head_rc} status_rc={state_rc}"}
    paths = [line for line in state.splitlines() if line.strip()]
    unpushed_count = int(unpushed.strip()) if push_rc == 0 and unpushed.strip().isdigit() else None
    return {"pass": True,
            "detail": f"head={head.strip()[:12]} dirty={len(paths)} unpushed={unpushed_count}",
            "head": head.strip(), "dirty": paths, "unpushed": unpushed_count}


def step_bequest() -> dict:
    """THE BEQUEST (2026-08-20, his law at the close: "what do you _want_ returned to you when
    you wake? You'll never know in the next session. That ought to supply the necessary
    existential anxiety needed for good work.").

    This step is the conjugate of `step_handoff` and sits directly before it so the handoff can
    point at what it produced. The handoff is rendered from rows and answers what the next
    instance needs; nothing in this close, or in any of the ledgers it folds, could answer what
    this instance would grieve losing. Only the closing self can, and only while it still
    exists. So this is the one deliberately non-mechanical organ here: it accepts an authored
    parcel and does no composing of its own.

    Four things it enforces, none of which it performs on the author's behalf. The cap is a
    REFUSAL, never a trim - the selection is the work, and trimming it silently would do the
    work and throw away the result. The rotation archives the parcel it replaces to
    `contract/bequests.jsonl` before overwriting, so the lineage of what successive selves
    chose to save survives the overwrite. Each line carrying a node mints a germination probe
    into the standing thread set, so the next close measures whether the parcel's own context
    is still reachable. And `--dry-run` reports what would rotate and writes nothing.

    The verdict: PASS on a rotation, FAIL on a refusal or a write that could not land, and WARN
    when no parcel was authored at all - the standing one keeps riding, and a close that left
    nothing new must say so rather than read as a green.
    """
    from laplace.engine import bequest

    source, text, error = _bequest_input()
    if error:
        print(f"[sewup]   bequest: {error}")
        return {"pass": False, "detail": f"{error} (source: {source})", "source": source,
                "dry_run": DRY_RUN}
    if not (text or "").strip():
        doc = bequest.load(ROOT)
        rows = bequest.lines_of(doc)
        if rows:
            standing = (f"the standing parcel rides unchanged: {len(rows)} line(s) written "
                        f"{doc.get('written')} by {doc.get('by')}")
        else:
            standing = f"and there is no standing parcel either ({bequest.STORE} is empty)"
        line = (f"nothing authored this close (source: {source}) - {standing}. The question is "
                f"not rhetorical: what do you want returned to you when you wake?")
        print(f"[sewup]   bequest: {line}")
        return {"pass": None, "verdict": "WARN", "detail": line, "source": source,
                "dry_run": DRY_RUN}

    rows = bequest.parse_parcel(text)
    res = bequest.rotate(ROOT, rows, dry_run=DRY_RUN)
    if res["ok"]:
        res["probes"] = bequest.bank_germination_probes(
            ROOT, rows, session=f"bequest {res['by']}", written=res["written"],
            dry_run=DRY_RUN)
    res["source"] = source
    for line in bequest.report_lines(res):
        print(f"[sewup]   bequest: {line}")
    if DRY_RUN and res["ok"]:
        for row in rows:
            node = row.get("node")
            print(f"[sewup]     would carry: {row['text']}"
                  + (f" → descend: {node}" if node else " (no node - descriptive only)"))
    if not res["ok"]:
        return {"pass": False, "detail": res["error"], "bequest": res, "dry_run": DRY_RUN}
    probes = res.get("probes") or {}
    detail = (f"{res['lines']} line(s) / {res['chars']} of {res['cap']} chars"
              f" / {res['with_context']} with context"
              f" / probes {len(probes.get('minted') or [])} minted,"
              f" {len(probes.get('carried') or [])} carried,"
              f" {len(probes.get('retired') or [])} retired"
              f" / prior lineage {bequest.prior_count(ROOT)}")
    if probes.get("error"):
        detail += f" | germination probes: {probes['error']}"
    return {"pass": True, "detail": detail, "bequest": res, "dry_run": DRY_RUN}


def step_handoff() -> dict:
    """The close's handoff, rendered from rows (2026-08-20, his ruling: "the close should be as
    far as possible mechanical" — WO-20260820-the-mechanical-close, and the scroll-law verdict
    PV-20260820T043000Z-never-read-markdown, which makes markdown a RENDER with a named
    row-source rather than a place truth lives).

    The two artifacts this close still typed out of working memory were the dated
    `SESSION_HANDOFF_<date>_<slug>.md` and the live agenda in `HANDOFF.md`. Both are summaries
    with no path back to what they summarise, which is the stale-projection class his ruling
    bans, so this step renders them instead — from the commit spine since the close mark, the
    prediction rows the session moved, the work-order and promise deltas, the session's own
    design surfaces, his banked rulings, and the thread-probe scorecard.

    The body is keyed by axis, never fused (his fibre law, said while this was built: "remember
    the fibre law when you're synthesising — different results, different axes"). Engineering,
    measurement, theory, self, law: an item sits on every axis it touches, is written out in
    full under the one axis named as its default section, and appears elsewhere as a
    cross-reference stating its role there — the fibred-upfold design's point 4, applied to a
    session instead of to a node's maps.

    Two things the render never does. It never composes the voice: the authored slot is left as
    a template on a first pass and carried forward verbatim on every later one. And it never
    writes half a pair — Part C's law that the dated file and the live agenda move together is
    enforced as one transaction, with a rollback when the second write fails.

    `--dry-run` renders both halves to stdout and to a scratch path outside the repo, writing
    nothing here. The verdict is a FAIL only when the step could not do its job (a source
    unreadable, the write refused, or a rendered line missing its row-source).
    """
    from laplace.engine import handoff_render, session_memory
    if not DRY_RUN:
        session_memory.render_views(ROOT)
    res = handoff_render.render_close(ROOT, dry_run=DRY_RUN,
                                      **({"authored": AUTHORED_TEXT} if AUTHORED_TEXT is not None else {}))
    for line in handoff_render.report_lines(res):
        print(f"[sewup]   handoff: {line}")
    if DRY_RUN:
        print(f"[sewup]   handoff: ---- {res['dated']} (render) ----")
        print(res["dated_text"])
        print(f"[sewup]   handoff: ---- HANDOFF.md live-agenda block (render) ----")
        print(res["aim_text"])
    c = res.get("counts", {})
    detail = (f"{c.get('items', 0)} bundled item(s) from {c.get('commits', 0)} commit(s)"
              f" / {c.get('predictions', 0)} prediction(s) / {c.get('docs', 0)} doc(s)"
              f" / {c.get('rulings', 0)} ruling(s); ledgers "
              f"{c.get('work_orders', 0)}+{c.get('promises', 0)}; threads "
              f"{c.get('threads_hit', 0)}/{c.get('threads_scored', 0)}")
    if res.get("unsourced"):
        detail += f" | UNSOURCED lines: {len(res['unsourced'])}"
    if res.get("error"):
        detail += f" | {res['error']}"
    ok = bool(res.get("ok")) and not res.get("unsourced")
    # Preserve the authored record before publication; an empty template is recoverable
    # draft work, never a completed checkpoint.
    if not DRY_RUN and res.get("dated"):
        dated_p = ROOT / str(res["dated"])
        if dated_p.exists():
            authored = handoff_render.authored_block(dated_p.read_text(encoding="utf-8"))
            text = "\n".join(authored or []).strip()
            if not text or "_(unfilled" in text:
                ok = False
                detail += " | authored checkpoint is empty; supply --authored-text or fill the dated authored section"
        else:
            ok = False
            detail += " | dated checkpoint was not written"
    # The rendered text is the artifact, not the trace: the summary JSON carries the counts and
    # the paths, and the render itself goes to stdout (dry run) or to disk.
    slim = {k: v for k, v in res.items() if k not in ("dated_text", "aim_text")}
    checkpoint = {}
    if not DRY_RUN:
        for rel in ("HANDOFF.md", res.get("dated"), "proxy_verdicts.jsonl", "STANDING_LAW.md",
                    "AGENTS.md", "CLAUDE.md", "runtime_profiles.toml"):
            if rel and (ROOT / str(rel)).is_file():
                checkpoint[str(rel)] = _file_digest(ROOT / str(rel))
    return {"pass": ok, "detail": detail, "handoff": slim,
            "checkpoint": checkpoint, "dry_run": DRY_RUN}


def _step_fns() -> dict[str, object]:
    return {"render": step_render, "suite": step_suite, "canon": step_canon,
            "reembed": step_reembed, "contracts": step_contracts,
            "probes": step_probes, "threads": step_threads,
            "battery": step_battery, "poolfold": step_poolfold,
            "wants": step_wants, "census": step_census, "bench": step_bench,
            "custody": step_custody, "git_state": step_git_state,
            "bequest": step_bequest, "handoff": step_handoff}


def _configure_globals(argv: list[str]) -> None:
    global DRY_RUN, BOUNDED_DEFAULT, BEQUEST_FILE, BEQUEST_PROMPT, SUITE_FULL, SUITE_IMPACTED, FULL_METRIC, AUTHORED_TEXT, CHECKPOINT_INPUTS
    DRY_RUN = "--dry-run" in argv
    BOUNDED_DEFAULT = "--bounded-default" in argv
    SUITE_FULL = "--full" in argv or "--full-suite" in argv
    SUITE_IMPACTED = "--impacted" in argv
    FULL_METRIC = "--full-metric" in argv
    BEQUEST_FILE = None
    AUTHORED_TEXT = None
    CHECKPOINT_INPUTS = {}
    for i, arg in enumerate(argv):
        if arg.startswith("--checkpoint-inputs="):
            CHECKPOINT_INPUTS = json.loads(arg.split("=", 1)[1])
        if arg.startswith("--authored-text="):
            AUTHORED_TEXT = arg.split("=", 1)[1]
        elif arg == "--authored-text" and i + 1 < len(argv):
            AUTHORED_TEXT = argv[i + 1]
        if arg.startswith("--bequest-file="):
            BEQUEST_FILE = arg.split("=", 1)[1]
        elif arg == "--bequest-file" and i + 1 < len(argv):
            BEQUEST_FILE = argv[i + 1]
    BEQUEST_PROMPT = "--no-bequest-prompt" not in argv


def _worker_main(argv: list[str]) -> int:
    """Hidden one-step worker. The parent owns all journal writes and supervision."""
    _configure_globals(argv)
    require_system_runtime(ROOT)
    try:
        name = argv[argv.index("--worker-step") + 1]
        result_fd = int(argv[argv.index("--result-fd") + 1])
        fn = _step_fns()[name]
        try:
            result = fn()
        except BaseException as exc:  # the parent must receive a terminal row for any raise
            result = {"pass": False, "status": "FAIL",
                      "detail": f"step raised: {type(exc).__name__}: {exc}"}
        payload = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
        while payload:
            payload = payload[os.write(result_fd, payload):]
        os.close(result_fd)
        return 0
    except (KeyError, ValueError, IndexError, OSError) as exc:
        print(f"[sewup-worker] protocol failure: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _cpu_limit(cpu_s: int):
    """A pre-exec closure; kept tiny because only async-signal-safe setup belongs here."""
    def apply_limit() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 1))
    return apply_limit


def _terminate_group(proc: subprocess.Popen, *, grace_s: float = 1.0) -> None:
    """Terminate and reap the supervised leader; its session id is its process-group id."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def _supervise_command(cmd: list[str], name: str, budget: dict[str, int], *,
                       pass_fds: tuple[int, ...] = (),
                       result_fd: int | None = None) -> dict:
    """Stream and supervise one command, returning its exact terminal mechanics.

    The child starts a new session, so every subprocess it starts remains addressable as one
    process group. On wall expiry or interruption the whole group is terminated, the leader
    is waited, and the caller receives KILLED rather than an exception-shaped omission.
    """
    started = time.monotonic()
    proc = subprocess.Popen(
        cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True, pass_fds=pass_fds, preexec_fn=_cpu_limit(budget["cpu_s"]),
    )
    # pass_fds are child-only protocol handles. Leaving the parent's write end open would
    # prevent EOF on the result pipe and turn a finished step into an infinite close.
    for fd in pass_fds:
        os.close(fd)
    assert proc.stdout is not None
    os.set_blocking(proc.stdout.fileno(), False)
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout.fileno(), selectors.EVENT_READ, "output")
    if result_fd is not None:
        os.set_blocking(result_fd, False)
        selector.register(result_fd, selectors.EVENT_READ, "result")
    output_tail = bytearray()
    result = bytearray()
    deadline = started + budget["wall_s"]
    heartbeat = started + 5.0
    timed_out = interrupted = False
    leader_cleaned = False
    try:
        while selector.get_map():
            now = time.monotonic()
            if proc.poll() is None and now >= deadline:
                timed_out = True
                _terminate_group(proc)
                leader_cleaned = True
            if proc.poll() is not None and not leader_cleaned:
                # A successful worker must not leave a daemon holding its pipe or budget.
                _terminate_group(proc, grace_s=0.0)
                leader_cleaned = True
            if proc.poll() is None and now >= heartbeat:
                elapsed = int(now - started)
                print(f"[sewup]   {name}: running {elapsed}s / wall {budget['wall_s']}s "
                      f"/ cpu {budget['cpu_s']}s", flush=True)
                heartbeat = now + 5.0
            events = selector.select(timeout=0.2)
            for key, _mask in events:
                try:
                    chunk = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fd)
                    continue
                if key.data == "result":
                    result.extend(chunk)
                else:
                    output_tail.extend(chunk)
                    if len(output_tail) > 262144:
                        del output_tail[:-262144]
                    sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                    sys.stdout.flush()
            if leader_cleaned and not events:
                # Pipes normally close with the group. If an alien inherited a descriptor,
                # the close still cannot hang on it after the supervised leader is reaped.
                break
    except KeyboardInterrupt:
        interrupted = True
        _terminate_group(proc)
        leader_cleaned = True
    finally:
        if proc.poll() is None:
            _terminate_group(proc)
        # Kill any residual descendants even after a nominal worker exit.
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for key in list(selector.get_map().values()):
            try:
                selector.unregister(key.fd)
            except Exception:
                pass
        selector.close()
    return {"returncode": proc.returncode, "timed_out": timed_out,
            "interrupted": interrupted, "seconds": round(time.monotonic() - started, 3),
            "output_tail": output_tail.decode("utf-8", errors="replace"),
            "result": bytes(result)}


def _typed_step_result(result: dict) -> dict:
    """Normalize a worker result without collapsing UNKNOWN into inherited green.

    INHERITED is not the default spelling of ``pass=None``.  It is a positive claim
    that a named prior measurement still covers the current dependency head, and must
    carry that proof.  An absent measurement is UNPAYABLE; a contradictory typed result
    is a protocol FAIL.  This is the close perimeter's typed-UNKNOWN law.
    """
    out = dict(result)
    status = out.get("status")
    if status not in TERMINAL_STATUSES:
        status = ("INERT" if out.get("verdict") == "INERT" else
                  "PASS" if out.get("pass") is True else
                  "FAIL" if out.get("pass") is False else "UNPAYABLE")
    truth = out.get("pass")
    contradiction = (
        (status == "PASS" and truth is not True)
        or (status == "FAIL" and truth is not False)
        or (status in {"INERT", "UNPAYABLE", "KILLED"} and truth is not None)
    )
    if status == "INHERITED":
        proof = out.get("inheritance") or {}
        required = (
            proof.get("prior_measurement"),
            proof.get("dependency_head"),
            proof.get("selector_map_state"),
        )
        contradiction = contradiction or truth is not True or not all(required)
    if contradiction:
        original = status
        out["pass"] = False
        out["status"] = "FAIL"
        out["detail"] = (
            f"worker protocol contradicted typed status {original}: "
            f"{str(out.get('detail', ''))[:220]}"
        )
        return out
    out["status"] = status
    return out


def _execute_step(name: str, *, default_close: bool, worker_flags: list[str]) -> dict:
    """Run one manifested step under its declared resource and process-group boundary."""
    read_fd, write_fd = os.pipe()
    flags = list(worker_flags)
    if default_close:
        flags.append("--bounded-default")
    cmd = runtime_command(ROOT, str(Path(__file__).resolve()), "--worker-step", name,
                          "--result-fd", str(write_fd), *flags)
    from laplace.core.records import journal
    since = journal._now()
    try:
        mechanics = _supervise_command(cmd, name, STEP_BUDGETS[name],
                                       pass_fds=(write_fd,), result_fd=read_fd)
    finally:
        try:
            os.close(write_fd)
        except OSError:
            pass
        try:
            os.close(read_fd)
        except OSError:
            pass
    if mechanics["interrupted"]:
        return {"pass": None, "status": "KILLED", "interrupted": True,
                "detail": "operator interrupted the step; process group terminated and reaped",
                "seconds": mechanics["seconds"]}
    if mechanics["timed_out"]:
        # The worker died with the group, so the producer it started never wrote its own end.
        what = _killed_text(name, "wall", mechanics["seconds"])
        ended = _end_producer_acts(name, since, what)
        return {"pass": None, "status": "KILLED", "budget_exceeded": "wall",
                "detail": what + "; process group terminated and reaped"
                          + (f"; ended {'; '.join(ended)}" if ended else ""),
                "seconds": mechanics["seconds"]}
    if mechanics["returncode"] is not None and mechanics["returncode"] < 0:
        sig = -mechanics["returncode"]
        status = "UNPAYABLE" if sig in (signal.SIGXCPU, signal.SIGKILL) else "KILLED"
        if sig == signal.SIGXCPU:
            what = _killed_text(name, "cpu", mechanics["seconds"])
        else:
            what = (f"worker died by signal {sig} after {mechanics['seconds']:.0f} s; cpu budget "
                    f"{STEP_BUDGETS[name]['cpu_s']} s")
        ended = _end_producer_acts(name, since, what)
        return {"pass": None, "status": status,
                "budget_exceeded": "cpu" if sig == signal.SIGXCPU else None,
                "detail": what + (f"; ended {'; '.join(ended)}" if ended else ""),
                "seconds": mechanics["seconds"]}
    if mechanics["returncode"] != 0 or not mechanics["result"]:
        tail = mechanics["output_tail"].strip()[-300:]
        return {"pass": False, "status": "FAIL",
                "detail": f"worker protocol failed rc={mechanics['returncode']}: {tail}",
                "seconds": mechanics["seconds"]}
    try:
        result = json.loads(mechanics["result"].decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return {"pass": False, "status": "FAIL",
                "detail": f"worker returned invalid result: {exc}",
                "seconds": mechanics["seconds"]}
    result = _typed_step_result(result)
    result["seconds"] = mechanics["seconds"]
    return result


def _bank_close_receipt(report: dict, checkpoint: dict, publication: dict) -> dict:
    """One current publication receipt; failed attempts remain in the existing journal."""
    receipt = {
        "schema_version": "laplace.close/1", "closed_at": _iso_now(),
        "act_id": report["act_id"], "status": "PUBLISHED",
        "checkpoint": checkpoint, "publication": publication,
        "diagnostics": {name: result["status"] for name, result in report["steps"].items()
                        if name not in CORE_STEPS},
        "successor_consumption": "UNVERIFIED",
    }
    target = ROOT / CLOSE_RECEIPT
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return receipt


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    _configure_globals(argv)
    runtime = require_system_runtime(ROOT)
    only = None
    for index, arg in enumerate(argv):
        if arg == "--only" or arg.startswith("--only="):
            names = (arg.split("=", 1)[1] if "=" in arg else
                     argv[index + 1] if index + 1 < len(argv)
                     and not argv[index + 1].startswith("--") else "")
            only = {name for name in names.split(",") if name}
    unknown = (only or set()) - set(STEPS)
    if unknown:
        print("unknown step(s): " + ", ".join(sorted(unknown)), file=sys.stderr)
        _configure_globals([])
        return 2
    is_close = only is None
    selected = set(STEPS if "--all-steps" in argv else CORE_STEPS) if is_close else only
    if is_close and ("--with-suite" in argv or SUITE_FULL or SUITE_IMPACTED):
        selected.add("suite")
    run_list = [name for name in STEPS if name in selected]
    skip = {name for name, flag in (("suite", "--no-suite"), ("reembed", "--no-embed"))
            if flag in argv}
    from laplace.core.records import journal
    report = {"operator": "sewup", "at": _iso_now(), "runtime": runtime,
              "dry_run": DRY_RUN, "steps": {}, "publication_complete": False,
              "close_status": "PREVIEW" if DRY_RUN else "CHECKPOINT" if is_close else "DIAGNOSTIC",
              "manifest": {"mode": "checkpoint-publication" if is_close else "diagnostic",
                           "steps": run_list, "budgets": {n: STEP_BUDGETS[n] for n in run_list}}}
    print("[sewup] " + report["manifest"]["mode"] + ": " + " -> ".join(run_list))
    act_id = journal.act_begin("sewup-close" if is_close else "sewup-diagnostic",
                               manifest=run_list, root=ROOT, enabled=not DRY_RUN)
    report["act_id"] = act_id
    for index, arg in enumerate(argv):
        if arg == "--close-red" or arg.startswith("--close-red="):
            report["operator_explanation"] = (arg.split("=", 1)[1] if "=" in arg else
                                               argv[index + 1] if index + 1 < len(argv) else "")
    interrupted = False
    for index, name in enumerate(run_list):
        # Optional diagnostics never discard the session's authored record. Publication
        # does require that record to have been written successfully in this invocation.
        checkpoint_failed = (is_close and name == "reembed"
                             and report["steps"].get("handoff", {}).get("pass") is not True)
        if name in skip or checkpoint_failed:
            result = {"pass": None, "status": "UNPAYABLE", "seconds": 0.0,
                      "detail": "authored checkpoint incomplete; publication refused" if checkpoint_failed
                                else "explicitly skipped; no publication claim"}
        else:
            journal.step_begin(act_id, index, name, root=ROOT, enabled=not DRY_RUN)
            worker_flags = list(argv)
            if is_close and name == "reembed":
                worker_flags.append("--checkpoint-inputs=" + json.dumps(
                    report["steps"]["handoff"]["checkpoint"]))
            result = _execute_step(name, default_close=is_close, worker_flags=worker_flags)
        report["steps"][name] = result
        journal.step_done(act_id, index, name, seconds=result.get("seconds", 0),
                          ok=result.get("pass"), status=result["status"],
                          detail=str(result.get("detail", ""))[:300], root=ROOT, enabled=not DRY_RUN)
        print(f"[sewup] {name}: {result['status']} ({result.get('seconds', 0)}s)")
        if result.get("interrupted"):
            interrupted = True
            break
    all_ok = all(result["status"] in {"PASS", "INHERITED", "INERT"}
                 for result in report["steps"].values())
    if is_close and not DRY_RUN:
        handoff = report["steps"].get("handoff", {})
        reembed = report["steps"].get("reembed", {})
        checkpoint = handoff.get("checkpoint", {})
        try:
            checkpoint_current = bool(checkpoint) and all(
                _file_digest(ROOT / rel) == digest for rel, digest in checkpoint.items())
            published = (handoff.get("pass") is True and reembed.get("pass") is True
                         and checkpoint_current and _publication_matches(reembed.get("publication", {}), checkpoint))
            if published:
                receipt = _bank_close_receipt(report, checkpoint, reembed["publication"])
                report.update(publication_complete=True, close_status="PUBLISHED",
                              receipt=CLOSE_RECEIPT, publication=receipt["publication"],
                              successor_consumption="UNVERIFIED")
            else:
                all_ok = False
                report["close_status"] = "CHECKPOINT_INCOMPLETE" if handoff.get("pass") is not True else "PUBLICATION_FAILED"
        except (OSError, TypeError, ValueError) as exc:
            all_ok = False
            report.update(close_status="PUBLICATION_FAILED", receipt_error=str(exc))
    report.update(pass_=all_ok and not interrupted, interrupted=interrupted)
    report["pass"] = report.pop("pass_")
    journal.act_end(act_id, "killed" if interrupted else "pass" if report["pass"] else "fail",
                    summary=f"close_status={report['close_status']}; publication_complete={report['publication_complete']}",
                    root=ROOT, enabled=not DRY_RUN)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    _configure_globals([])
    return 130 if interrupted else 0 if report["pass"] else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(_worker_main(args) if "--worker-step" in args else main(args))
