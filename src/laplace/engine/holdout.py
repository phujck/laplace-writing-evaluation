"""holdout.py - F25 automated: prior-me predicts next-me, banked in-repo, scored at wake.

The hold-out was the apex fitness signal carried in GERARD'S memory between sessions
(OPEN_STACK F25: "banked nowhere... scored on wake"). His ruling (2026-07-11, the website
session): automate the courier. The close BANKS a prediction file; the next wake SCORES it.

Two prediction classes, because blindness only matters for one:
- MECHANICAL: facts of the environment next-me cannot fake by knowing them (a TeX verdict
  line exists or it does not; a command exits 0 or it does not). Scored automatically at
  wake by running each check. Contamination-immune.
- BEHAVIORAL: claims about what next-me will DO or MISS. The wake prints their IDS ONLY -
  the claim text is withheld from wake output so the session runs practically blind; the
  text is scored at the NEXT CLOSE against the session that actually happened.

Stated limit (in the file header too): the pending file is committed in plain - a next-me
that goes looking can read the behavioral claims early. Blindness here is covenant-backed
(the wake surfaces ids only; the close scores), not cryptographic. If the pattern-read
ever matters enough to seal, site_seal is sitting right there; v1 chooses legible over
locked, per earned simplicity.

The wake NEVER fails on this machinery - every path is swallowed (the hello covenant).

Convention banked here: wake/env mechanical probes use the ``scripts/*.py`` cold transport
(``python3 scripts/wake.py``), never ``uv run ...`` - the cold-wake case is exactly the
no-warm-env case, and an env sync inside a probe measures the installer, not the wake.

The aggregate budget (2026-08-19, the cold-wake cure). ``score_mechanical`` used to carry a
120 s ceiling PER CHECK and no ceiling at all across them, while riding the wake's hot path.
That is an unbounded scorecard on a bounded transport: the 2026-07-21 pending file banked two
probes that each boot a scanner, ``sleep 5``, then drive a real headless-Chrome scroll-law walk
(4 and 24 page loads), so every wake on every box paid 25-100 s to re-score a four-week-old
prediction - measured 101.9 s of a 102.7 s profiled wake, against 0.79 s for the wake's own
projection. Any close could bank an arbitrarily expensive probe and silently make every
subsequent wake minutes long. The scorecard now runs under a total wall budget
(``WAKE_BUDGET_S``); checks it cannot afford are reported ``BUDGET`` and are NEVER silently
dropped, because a scorecard that quietly shrinks is worse than one that says it ran out of
room. ``budget_s=None`` lifts the aggregate budget for the close's own scoring (``archive``),
which is not a wake and must score for real before it clears the pending file.

The thread probes (2026-08-19, the design-thread miss). EIGEN_PROTOCOL Part C ends the close
with "the rehearsal - the wake re-fired and read back as the stranger": qualitative, unscored,
and therefore blind to the failure the bench in
``evidence/RECONSTRUCTION_BENCH_2026-08-19_design-thread-miss/`` measured - threads PRESENT and
VERBATIM-NAMED in the corpus (DMRG, orthogonality catastrophe, the loss Hamiltonian, the closure
residual) that neither the wake nor the router could reach. Nothing at any close would have
caught it. A ``thread_probe`` makes that same question mechanical and standing:

    {"id", "query", "must_reach": [path fragments], "top_k", "expected_now": "pass"|"fail"}

scored by firing ``embed_router.route`` on the LIVE network and asking whether any ``must_reach``
fragment appears among the top-k files. The meter-faithfulness law (SESSION_HANDOFF_2026-06-06,
the 2-shingle lesson) is why this calls the real router rather than a lexical stand-in: a probe
that measures a proxy measures the proxy.

``expected_now`` is the same law ``scripts/sewup.py``'s banked suite baseline runs on: a red that
is a KNOWN red is not an alarm, it is the state of the cure. A probe stamped ``fail`` that still
misses is reported and passes the close; one that starts HITTING is CLEARED - improvement, named
for a deliberate re-stamp, never auto-shrunk. A probe stamped ``pass`` that starts missing is a
REGRESSION and fails the close: the reachability the corpus HAD has been lost.

They ride the same aggregate wall as the mechanical checks (one ``Wall`` shared across the whole
wake scorecard) with the same stated ``BUDGET`` verdict. In practice the 5 s wake wall cannot pay
for live routing at all (the floors above), so the wake reports the LAST CLOSE'S scores, stamped
``live: false`` with the date they were taken - the fallback that labels itself, and strictly
more than a bare BUDGET line. Live scoring is the CLOSE's job (no wall there, exactly like
``archive``).
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

PENDING = "holdout/PREDICTION_pending.json"
#: The STANDING thread probes (see "The thread probes" below). A separate file from
#: ``PENDING`` on purpose: ``archive()`` unlinks the pending prediction at every close, and a
#: standing instrument that deletes itself the first time it is used is not an instrument.
THREAD_PROBES = "holdout/THREAD_PROBES.json"
#: SCORING IS ONE ACT WITH ITS DEPOSIT (WO-20260817-holdout-scores-deposit, the thin-systems
#: audit 2026-08-17). The wake scored the author's verbatim holdout, PRINTED the verdicts - and
#: recorded nothing, so the close's own holdout check had nothing to read and fell back to
#: comparing file mtimes, which can only ever WARN. A wake that scores now BANKS what it scored
#: here, and ``close_checklist.check_holdout`` reads THESE VERDICTS instead of guessing from
#: timestamps. Gitignored on purpose: it is a per-machine, per-wake deposit (regenerated by the
#: next wake), and a tracked file rewritten every wake would arm close_beats' holdout-intake beat
#: at every close - a forged "the holdout machinery moved" signal, which is precisely the class of
#: defect this row closes. The SETTLED record still travels: ``archive()`` folds the scores into
#: the tracked ``holdout/SCORED_<ts>.json`` at the close.
LAST_SCORE = "holdout/LAST_SCORE.json"

# The per-check ceiling (unchanged) and the aggregate wall budget across ALL checks. The
# aggregate is what makes "the wake transport is seconds" true by construction instead of by
# hoping nobody banks a browser walk; it also CLAMPS each check's own timeout to whatever
# budget is left, so one slow probe cannot spend the whole wall by itself.
CHECK_TIMEOUT_S = 120
WAKE_BUDGET_S = 5.0

# The thread probes route IN-PROCESS (the real router, not a proxy), and an in-process call
# cannot be preempted mid-flight the way a subprocess can be killed at its clamp. So the wall
# is honoured at the DOOR instead: a step whose measured floor the remaining wall cannot pay is
# refused BEFORE it starts and reported BUDGET. Floors measured on this box at the 2026-08-19
# GPU-seam HEAD: conceptric.load_network 5.5 s (cold, once), embed_router.route 2.4-2.8 s each.
THREAD_LOAD_FLOOR_S = 8.0     # the network load + one route: the cheapest useful live scoring
THREAD_ROUTE_FLOOR_S = 2.5    # one further route once the network is up
#: How many probes one close may MINT from new DESIGN_/ARMING_ docs. Bounded because each mint
#: costs a live route to stamp its expected_now honestly; the remainder is NAMED, never dropped.
MINT_CAP = 3
#: The doc classes a close mints from, at the repo root where they live.
MINT_GLOBS = ("DESIGN_*.md", "ARMING_*.md", "SYNTHESIS_*.md")
#: How many title words a minted query keeps (headings here run to two lines).
TITLE_TERM_WORDS = 16

_HEADER_NOTE = (
    "F25 automated. Mechanical checks score at wake; behavioral claims score at the next "
    "close - next-me: the wake shows you behavioral IDS ONLY on purpose; reading the "
    "claims early breaks your own blindness. Covenant, not cryptography."
)


class Wall:
    """The aggregate wall budget, as an object so ONE wall spans the whole wake scorecard.

    The budget exists to make "the wake transport is seconds" true by construction. That claim
    is only true if every scorer on the wake shares one wall: two scorers each honouring 5 s
    is a 10 s wake. ``score_mechanical`` and ``score_threads`` therefore take an optional
    ``wall=`` and the wake builds exactly one. ``budget_s=None`` means no wall at all - the
    close, which is not a wake and must score for real.
    """

    def __init__(self, budget_s: float | None = WAKE_BUDGET_S) -> None:
        self.budget_s = budget_s
        self.started = time.monotonic()
        self.deadline = None if budget_s is None else self.started + budget_s

    def remaining(self) -> float | None:
        return None if self.deadline is None else self.deadline - time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def affords(self, floor_s: float) -> bool:
        """True iff the wall can pay a step whose measured floor is ``floor_s``."""
        r = self.remaining()
        return r is None or r >= floor_s

    def block(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """The budget stanza that rides every verdict: a reader must be able to tell a
        scorecard that RAN from one that ran out of wall. ``UNPAYABLE`` (HOT-3, 2026-08-20) is
        the door-refused sibling of ``BUDGET`` - a check whose own declared floor could not fit
        the remaining wall - and counts the same way toward "this scorecard could not pay for
        everything"."""
        return {"seconds": self.budget_s, "elapsed": round(self.elapsed(), 2),
                "spent": any(r.get("verdict") in ("BUDGET", "UNPAYABLE") for r in results)}


def bank(repo_root: Path | str, session: str, mechanical: list[dict[str, Any]],
         behavioral: list[dict[str, Any]]) -> Path:
    """Bank the close-time prediction. mechanical: [{id, cmd, expect: 'rc0'|substring}];
    behavioral: [{id, claim}]. Overwrites any un-scored pending (the new close supersedes)."""
    root = Path(repo_root)
    p = root / PENDING
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "note": _HEADER_NOTE,
        "banked": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session": session,
        "mechanical": mechanical,
        "behavioral": behavioral,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def load_pending(repo_root: Path | str) -> dict[str, Any] | None:
    p = Path(repo_root) / PENDING
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _kill_group(proc: "subprocess.Popen[str]") -> None:
    """Kill the check's whole process group where the OS has one; the shell alone otherwise."""
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
    except OSError:  # already reaped, or no such group - fall through to the plain kill
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _run_check(cmd: str, root: Path, timeout: float) -> subprocess.CompletedProcess:
    """One check, run like ``subprocess.run`` with one addition: the child gets its OWN process
    group and a timeout kills the GROUP, not just the shell.

    The banked probes background a server and clean it up in their own trailer
    (``... & S=$!; sleep 5; <walk>; kill $S``). A plain ``run(timeout=...)`` kills the shell
    before that trailer can execute and leaves the server bound to its port forever - so the
    budget would trade a slow wake for a leaked daemon on every wake. It does not.
    """
    kw: dict[str, Any] = {"start_new_session": True} if os.name == "posix" else {}
    proc = subprocess.Popen(cmd, shell=True, cwd=str(root), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True,
                            # recursion guard: a probe that wakes the waker must not re-score
                            # the probes - the scorecard never reads itself. The child sees the
                            # sentinel and skips its own holdout-scoring block (wake.py main
                            # checks LAPLACE_WAKE_SCORING).
                            env={**os.environ, "LAPLACE_WAKE_SCORING": "1"}, **kw)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - the group refused to die
            pass
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def score_mechanical(repo_root: Path | str, *,
                     budget_s: float | None = WAKE_BUDGET_S,
                     wall: Wall | None = None) -> dict[str, Any] | None:
    """Run every mechanical check; return the verdict block the wake prints. Never raises.

    ``budget_s`` is the AGGREGATE wall budget across all checks (see the module header). A
    check the budget cannot pay for is reported with verdict ``BUDGET`` and a detail that says
    so - it is never dropped, and BUDGET is not PASS. ``budget_s=None`` means no aggregate
    budget: that is the close's own scoring (``archive``), which is not on any hot path and
    must actually score the prediction before it clears the pending file.

    ``wall`` passes an ALREADY-RUNNING :class:`Wall` in, so this scorecard and the thread
    probes share one budget instead of one each (see :class:`Wall`).

    HOT-3 preflight (2026-08-20 self-audit): a check may bank an optional ``min_s`` beside its
    ``cmd`` - its own KNOWN floor cost (the two scroll-law probes banked 2026-07-21 both open
    with ``sleep 5``, so their floor is exactly 5s). When the remaining wall cannot pay that
    floor, the check is refused at the DOOR - never spawned - and reported ``UNPAYABLE``: named,
    loud, and zero-cost, instead of burning the wall to discover the same non-payability via a
    timeout (the failure mode this preflight replaces: the old path spent the whole 5s wall
    inside ``sleep 5`` before ever reporting anything). A check with no ``min_s`` declared keeps
    the old best-effort behaviour (clamp-and-try) - this is additive, not a new requirement on
    every banked check.
    """
    pending = load_pending(repo_root)
    if not pending:
        return None
    root = Path(repo_root)
    results: list[dict[str, Any]] = []
    wall = wall if wall is not None else Wall(budget_s)
    budget_s = wall.budget_s
    for check in pending.get("mechanical", []):
        cid, cmd, expect = check.get("id", "?"), check.get("cmd", ""), check.get("expect", "rc0")
        min_s = check.get("min_s")
        timeout, clamped = CHECK_TIMEOUT_S, False
        if wall.deadline is not None:
            remaining = wall.remaining() or 0.0
            if remaining <= 0:
                # LOUD, never silent: the check is named as unrun, with the reason.
                results.append({"id": cid, "verdict": "BUDGET",
                                "detail": f"not run: the {budget_s:g}s aggregate wall budget was "
                                          "spent by earlier checks"})
                continue
            if min_s is not None and remaining < min_s:
                # The door-check: this check's own declared floor cannot fit what is left of the
                # wall, so refuse it BEFORE spawning - zero cost, and a truer verdict than BUDGET
                # (which implies the wall ran dry; this one says the check was never payable to
                # begin with, at this position in the scorecard).
                results.append({"id": cid, "verdict": "UNPAYABLE",
                                "detail": f"not run: this check's known floor is {min_s:g}s but "
                                          f"only {remaining:.1f}s of the {budget_s:g}s aggregate "
                                          "wall remains - refused before spawning, never spent "
                                          "discovering it"})
                continue
            timeout, clamped = min(CHECK_TIMEOUT_S, remaining), remaining < CHECK_TIMEOUT_S
        verdict, detail = "ERROR", ""
        try:
            r = _run_check(cmd, root, timeout)
            if expect == "rc0":
                verdict = "PASS" if r.returncode == 0 else "FAIL"
                detail = f"rc={r.returncode}"
            else:
                hit = expect in (r.stdout + r.stderr)
                verdict = "PASS" if hit else "FAIL"
                detail = f"substring {'found' if hit else 'ABSENT'}: {expect!r}"
        except subprocess.TimeoutExpired as exc:
            # A timeout at the CLAMP is the budget speaking, not the check failing - say which.
            if clamped:
                verdict = "BUDGET"
                detail = (f"cut at {timeout:.1f}s: the {budget_s:g}s aggregate wall budget ran out "
                          f"inside this check (per-check ceiling {CHECK_TIMEOUT_S}s)")
            else:
                verdict, detail = "ERROR", f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 - a broken check is a FAIL-shaped fact, never a wake-breaker
            verdict, detail = "ERROR", f"{type(exc).__name__}: {exc}"
        results.append({"id": cid, "verdict": verdict, "detail": detail})
    block = {
        "banked": pending.get("banked"),
        "session": pending.get("session"),
        "mechanical": results,
        # the budget is part of the verdict, not a hidden setting: a reader must be able to
        # tell a scorecard that ran from one that ran out of wall.
        "budget": wall.block(results),
        # ids only - the claims stay unread at wake (the practical blindness)
        "behavioral_pending": [b.get("id", "?") for b in pending.get("behavioral", [])],
    }
    # THE DEPOSIT (WO-20260817-holdout-scores-deposit): scoring and banking what was scored are
    # ONE act. Printing a verdict nobody records is how the close ended up comparing mtimes.
    # Never fatal - a scorecard that cannot write its deposit still returns its verdicts.
    try:
        p = root / LAST_SCORE
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({**block, "scored_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return block


def archive(repo_root: Path | str, behavioral_scores: list[dict[str, Any]]) -> Path | None:
    """At the next close: fold the wake's mechanical scores + the session-end behavioral
    scores into holdout/SCORED_<ts>.json and clear the pending file."""
    root = Path(repo_root)
    pending = load_pending(root)
    if not pending:
        return None
    # No aggregate budget here: the close is not a wake. This call is the ONE place the
    # prediction is actually settled before the pending file is unlinked, so a BUDGET-truncated
    # fold would archive unscored checks as if they had been scored. The per-check ceiling
    # (CHECK_TIMEOUT_S) still bounds each probe, exactly as it did before the budget existed.
    mech = score_mechanical(root, budget_s=None) or {}
    out = root / "holdout" / f"SCORED_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({
        "prediction": pending,
        "mechanical_scores": mech.get("mechanical", []),
        "behavioral_scores": behavioral_scores,
        "scored": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (root / PENDING).unlink(missing_ok=True)
    # the per-wake deposit describes the prediction just settled; clearing it with the pending
    # file keeps the close's holdout check from reading a scorecard for a prediction that is
    # now archived (the SCORED_<ts>.json above is that prediction's permanent record).
    (root / LAST_SCORE).unlink(missing_ok=True)
    return out


# --------------------------------------------------------------------------------------- #
# THE THREAD PROBES - the rehearsal made quantitative (see the module header).
# --------------------------------------------------------------------------------------- #

_THREAD_NOTE = (
    "The standing thread probes: each row claims a QUERY reaches a NODE through the real "
    "router (embed_router.route on the live network, top_k). expected_now is the banked known "
    "state, exactly like the suite baseline - a known red is the state of a cure, not an alarm; "
    "a red that clears is named for a deliberate re-stamp; an expected PASS that starts missing "
    "is a REGRESSION and fails the close. Scored live at the close (scripts/sewup.py --only=threads); "
    "the wake reports these scores stamped with the date they were taken."
)


def load_probes(repo_root: Path | str) -> dict[str, Any] | None:
    p = Path(repo_root) / THREAD_PROBES
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_probes(repo_root: Path | str, doc: dict[str, Any]) -> Path:
    p = Path(repo_root) / THREAD_PROBES
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {**doc, "note": _THREAD_NOTE}
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def bank_probes(repo_root: Path | str, session: str, probes: list[dict[str, Any]], *,
                replace: bool = False) -> Path:
    """Bank or EXTEND the standing probe set. Unlike ``bank`` (which supersedes the pending
    prediction wholesale) the default here is additive and de-duplicated by id: the standing
    instrument accumulates across closes, and a close that mints a new probe must never
    silently drop the ones that measure the older threads. ``replace=True`` is the deliberate
    re-stamp."""
    doc = (None if replace else load_probes(repo_root)) or {
        "banked": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": session, "probes": [],
    }
    by_id = {p.get("id"): p for p in doc.get("probes", [])}
    for p in probes:
        by_id[p.get("id")] = {**by_id.get(p.get("id"), {}), **p}
    doc["probes"] = list(by_id.values())
    doc["session"] = session
    doc.setdefault("banked", time.strftime("%Y-%m-%dT%H:%M:%S"))
    doc["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return save_probes(repo_root, doc)


def _reach(files: list[dict[str, Any]], must_reach: list[str]) -> str | None:
    """The hit rule: any must_reach fragment appearing in any returned file path (the whole
    match is reported, so the record says WHICH target answered)."""
    for f in files:
        name = str(f.get("file", ""))
        for frag in must_reach:
            if frag and frag.lower() in name.lower():
                return name
    return None


def _in_corpus(net: dict[str, Any], must_reach: list[str]) -> bool:
    """Is any must_reach target even a MEMBER of the live network? A target the corpus does
    not contain cannot be routed to, and reporting that as a routing miss would mis-name the
    cure (ingest first, then rank). Meter faithfulness: say which failure this is."""
    for node in (net.get("nodes") or {}).values():
        for m in node.get("members", []) or []:
            for frag in must_reach:
                if frag and frag.lower() in str(m).lower():
                    return True
    return False


def _family_dial() -> float:
    """P26's declared dial (amendable only by row): hit-family membership = pairwise
    node-embedding cosine at or above this."""
    return float(os.environ.get("LAPLACE_FAMILY_COS", "0.95"))


def _collapse_families(repo_root: Path | str, net: dict[str, Any], router: Any,
                       files: list[dict], top_k: int) -> list[dict]:
    """P26's hit-family collapse, hottest-first over route's own ranking: a hit whose
    node embedding sits within the dial of an already-kept hit joins that family and is
    dropped; a hit with no vector is KEPT (never silently evicted - the eviction clause
    makes a collapsed true hit a named failure, so ambiguity keeps)."""
    import numpy as np
    dial = _family_dial()
    vecs = router.basis(repo_root, net, router.get_backend())["vectors"]
    kept: list[tuple[dict, Any]] = []
    for f in files:
        if len(kept) >= top_k:
            break
        v = vecs.get(str(f.get("file", "")))
        if v is None:
            kept.append((f, None))
            continue
        v = np.asarray(v, dtype=np.float64)
        n = float(np.linalg.norm(v))
        if n:
            v = v / n
        if any(kv is not None and float(kv @ v) >= dial for _, kv in kept):
            continue
        kept.append((f, v))
    return [f for f, _ in kept]


def score_threads(repo_root: Path | str, *, budget_s: float | None = WAKE_BUDGET_S,
                  wall: Wall | None = None, record: bool = False,
                  net: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Score the standing thread probes against the LIVE router. Never raises.

    Returns the verdict block (or None when no probe set is banked). Verdicts per probe:
    ``HIT`` / ``MISS`` / ``BUDGET`` (the wall could not pay for it) / ``ERROR`` (the router or
    the network was unavailable - never a pass). ``record=True`` writes the run back into the
    probe file as ``last_scored``, which is what the NEXT close diffs against; the wake never
    records (it is a reader, and a budget-clipped wake must not overwrite a real close's
    scores).

    ``net`` lets a caller that already holds the network hand it in rather than paying a second
    ``load_network`` (the close's threads step scores and then mints, and both used to load their
    own). The network is loaded lazily and once when it is not supplied, exactly as before, and a
    supplied one skips the load floor - there is no load left to afford.
    """
    doc = load_probes(repo_root)
    if not doc:
        return None
    probes = list(doc.get("probes") or [])
    wall = wall if wall is not None else Wall(budget_s)
    last = doc.get("last_scored") or {}
    prev = dict(last.get("by_id") or {})
    results: list[dict[str, Any]] = []
    router: Any = None
    dead: str | None = None                     # a load failure, applied to every later probe
    if net is not None:
        from laplace.representation import embed_router
        router = embed_router

    for probe in probes:
        pid = str(probe.get("id", "?"))
        query = str(probe.get("query", ""))
        must_reach = [str(x) for x in (probe.get("must_reach") or [])]
        top_k = int(probe.get("top_k") or 5)
        expected = str(probe.get("expected_now", "fail"))
        row: dict[str, Any] = {"id": pid, "expected_now": expected, "was": prev.get(pid)}
        if dead:
            row.update(verdict="ERROR", detail=dead)
            results.append(row)
            continue
        if net is None:
            if not wall.affords(THREAD_LOAD_FLOOR_S):
                row.update(verdict="BUDGET",
                           detail=f"not run: live routing needs ~{THREAD_LOAD_FLOOR_S:g}s "
                                  f"(network load + one route) and the "
                                  f"{wall.budget_s:g}s aggregate wall has "
                                  f"{max(wall.remaining() or 0.0, 0.0):.1f}s left")
                results.append(row)
                continue
            try:
                from laplace.engine import conceptric  # local: heavy, and only here
                from laplace.representation import embed_router
                net = conceptric.load_network(Path(repo_root))
                router = embed_router
            except Exception as exc:  # noqa: BLE001 - never a wake-breaker
                dead = f"network/router unavailable: {type(exc).__name__}: {exc}"
                row.update(verdict="ERROR", detail=dead)
                results.append(row)
                continue
        if not wall.affords(THREAD_ROUTE_FLOOR_S):
            row.update(verdict="BUDGET",
                       detail=f"not run: one route needs ~{THREAD_ROUTE_FLOOR_S:g}s and the "
                              f"{wall.budget_s:g}s aggregate wall has "
                              f"{max(wall.remaining() or 0.0, 0.0):.1f}s left")
            results.append(row)
            continue
        try:
            t0 = time.monotonic()
            if os.environ.get("LAPLACE_COLLAPSE_FAMILIES") == "1":
                # P26's serve-side ARM (an arm flag, NEVER a serving default - the judge's
                # confound guard (a): no cure becomes the incumbent mid-experiment): route a
                # wider pool, collapse hit-families (pairwise node-embedding cosine >= the
                # declared dial), keep the hottest member per family, serve top_k survivors.
                r = router.route(Path(repo_root), net, query, limit=top_k * 5)
                pool = list(((r or {}).get("files") or []))
                files = _collapse_families(repo_root, net, router, pool, top_k)
                row["collapse_arm"] = {"dial_cos": _family_dial(), "pool": len(pool),
                                       "kept": [str(f.get("file", "?")) for f in files]}
            else:
                r = router.route(Path(repo_root), net, query, limit=top_k)
                files = list(((r or {}).get("files") or []))[:top_k]
            row["seconds"] = round(time.monotonic() - t0, 2)
            if r is None:
                row.update(verdict="ERROR",
                           detail="route() returned None - no embedding backend on this box; "
                                  "the probe measures the real router or it measures nothing")
            else:
                hit = _reach(files, must_reach)
                row["top_k"] = [str(f.get("file", "?")) for f in files]
                if hit:
                    row.update(verdict="HIT", detail=f"reached {hit}")
                elif not _in_corpus(net, must_reach):
                    row.update(verdict="MISS",
                               detail="target ABSENT from the live network (not ingested) - "
                                      "the cure is a reembed before it is a ranking fix")
                else:
                    row.update(verdict="MISS",
                               detail=f"present in the corpus, unreached in top-{top_k}")
        except Exception as exc:  # noqa: BLE001
            row.update(verdict="ERROR", detail=f"{type(exc).__name__}: {exc}")
        results.append(row)

    for row in results:
        row["status"] = _thread_status(row)

    scored = [r for r in results if r["verdict"] in ("HIT", "MISS")]
    hits = [r for r in scored if r["verdict"] == "HIT"]
    cleared = [r["id"] for r in results if r["status"] == "CLEARED"]
    regressions = [r["id"] for r in results if r["status"] == "REGRESSION"]
    unrun = [r["id"] for r in results if r["verdict"] in ("BUDGET", "ERROR")]
    live = bool(scored)
    block: dict[str, Any] = {
        "banked": doc.get("banked"),
        "session": doc.get("session"),
        "live": live,
        "probes": results,
        "summary": {"total": len(results), "scored": len(scored), "hit": len(hits),
                    "red": len(scored) - len(hits), "unrun": unrun,
                    "cleared": cleared, "regressions": regressions},
        "headline": _thread_headline(results, scored, hits, cleared, regressions, last),
        "budget": wall.block(results),
        # ALWAYS carried: when the wall cannot pay for live routing (every wake, by the floors
        # above) this is the honest thing to read instead of a bare BUDGET line.
        "last_close": last or None,
        "delta": _thread_delta(results, prev),
    }
    if record and live:
        # THE STAMP SURVIVES THE CLOSE (the third judge's rider 2 at the 2026-08-24 close):
        # a bare {at, by_id} overwrite would re-open the unstamped-last_scored defect the
        # milestone-one grant killed - every recorded score now carries its own minimal
        # referent {head, tree_mtime, posture}, and a previously GRANTED referent_stamp is
        # preserved beside the update as prior_granted_stamp rather than silently erased.
        stamp: dict[str, Any] = {"posture": "close threads step (score_threads record=True)"}
        try:
            from laplace.core import versioning as gitio
            stamp["head"] = (gitio.head_sha(repo_root) or "?")[:8]
        except Exception:  # noqa: BLE001 - the stamp never breaks the scorecard
            stamp["head"] = "?"
        try:
            import datetime as _dt
            tree_p = Path(repo_root) / ".meaning_tree.json"
            stamp["tree_mtime_utc"] = _dt.datetime.fromtimestamp(
                tree_p.stat().st_mtime, _dt.timezone.utc).isoformat()
        except OSError:
            stamp["tree_mtime_utc"] = None
        prior_grant = (doc.get("last_scored") or {}).get("referent_stamp")
        doc["last_scored"] = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "scored": len(scored), "hit": len(hits),
            "by_id": {r["id"]: r["verdict"] for r in results},
            "referent_stamp": stamp,
            **({"prior_granted_stamp": prior_grant} if prior_grant else {}),
        }
        try:
            save_probes(repo_root, doc)
        except OSError:  # noqa: BLE001 - a scorecard never breaks its caller
            pass
    return block


def _thread_status(row: dict[str, Any]) -> str:
    """The banked-baseline law, per probe (mirrors sewup's suite baseline)."""
    verdict, expected = row.get("verdict"), row.get("expected_now", "fail")
    if verdict == "HIT":
        return "as-expected" if expected == "pass" else "CLEARED"
    if verdict == "MISS":
        return "REGRESSION" if expected == "pass" else "expected-red"
    return verdict or "ERROR"


def _thread_delta(results: list[dict[str, Any]], prev: dict[str, str]) -> list[str]:
    """What CHANGED since the last recorded close - the line the close prints.

    A probe the wall never RAN (BUDGET/ERROR) has no new verdict, so it cannot have changed:
    reporting "MISS -> BUDGET" would dress the budget up as a result. Unrun rows are carried in
    ``summary.unrun`` instead, where they read as what they are.
    """
    out = []
    for r in results:
        was, now = prev.get(r["id"]), r["verdict"]
        if now not in ("HIT", "MISS"):
            continue
        if was is None:
            out.append(f"{r['id']}: NEW -> {now}")
        elif was != now:
            out.append(f"{r['id']}: {was} -> {now}")
    for pid in prev:
        if not any(r["id"] == pid for r in results):
            out.append(f"{pid}: RETIRED (was {prev[pid]})")
    return out


def _thread_headline(results: list[dict[str, Any]], scored: list[dict[str, Any]],
                     hits: list[dict[str, Any]], cleared: list[str],
                     regressions: list[str], last: dict[str, Any]) -> str:
    """One line, truthful in both directions: a known red says so, and says the cure is pending."""
    if not scored:
        why = results[0].get("detail", "not scored") if results else "no probes banked"
        if not last:
            return f"not scored live ({why}); no banked close score to fall back on"
        # The fallback carries the SAME framing the live line does - a wake that reports "3 red"
        # without saying which of them are the banked known reds reads as an alarm, and this
        # instrument's whole point is telling a pending cure from a defect. Free: the verdicts
        # come from the last close's record, the expectations from the probe rows themselves.
        red = [r for r in results if r.get("was") == "MISS"]
        stale_regressions = [r["id"] for r in red if r.get("expected_now") == "pass"]
        line = (f"not scored live ({why}); at the {last.get('at', '?')} close: "
                f"{last.get('hit', '?')}/{last.get('scored', '?')} threads reached")
        if red:
            expected = len(red) - len(stale_regressions)
            line += (f", {len(red)} red"
                     + (f" ({expected} expected, the cure is pending)" if expected else ""))
        if stale_regressions:
            line += " | REGRESSION at that close: " + ", ".join(stale_regressions)
        return line
    red = len(scored) - len(hits)
    line = f"{len(hits)}/{len(scored)} thread probes reached"
    if red:
        expected_red = sum(1 for r in scored if r["status"] == "expected-red")
        line += (f" - {red} still red"
                 + (f" ({expected_red} expected, the cure is pending)" if expected_red else ""))
    if regressions:
        line += f" | REGRESSION ({len(regressions)}): " + ", ".join(regressions)
    if cleared:
        line += (f" | CLEARED ({len(cleared)}) - improvement; re-stamp expected_now at a clean "
                 f"close: " + ", ".join(cleared))
    return line


# --------------------------------------------------------------------------------------- #
# Minting: a new DESIGN_/ARMING_ doc mints its own probe, mechanically.
# --------------------------------------------------------------------------------------- #

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_CLASS_RE = re.compile(r"^\s*(DESIGN|ARMING|RULING|AUDIT)\b[\s—–-]*", re.I)


def probe_id_for(path: Path | str) -> str:
    """The probe id a doc mints under - stable, so re-minting is a no-op, not a duplicate."""
    stem = Path(path).stem
    return "thread-" + re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def title_terms(path: Path) -> str:
    """The query a doc mints: its own H1 title terms, class word and date stripped (they are
    filing metadata, not concepts), falling back to the filename tail. This is the CONCEPTUAL
    vocabulary the design-thread miss showed does not survive into handles - which is exactly
    why the probe asks whether it can be routed to."""
    title = ""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
    except OSError:
        title = ""
    if not title:  # no H1: the filename tail is the only title there is
        title = _DATE_RE.sub("", path.stem).replace("_", " ").replace("-", " ")
    title = _CLASS_RE.sub("", title)
    title = _DATE_RE.sub("", title).strip(" —–-:")
    # Bounded: a heading that runs to two lines (they do) would otherwise become a query whose
    # tail is filing punctuation. Words, not characters, so the cut lands on a concept.
    words = title.split()[:TITLE_TERM_WORDS]
    return " ".join(words).strip(" ;,:—–-(") or path.stem


def mint_candidates(repo_root: Path | str, *, since: str | None = None) -> list[Path]:
    """Docs eligible to mint: DESIGN_/ARMING_ at the root whose FILENAME DATE is >= ``since``.
    The filename date (not mtime) is the watermark because a fresh clone rewrites every mtime
    to checkout time - the same class of artefact the stale-metric warning names."""
    root = Path(repo_root)
    out = []
    for pattern in MINT_GLOBS:
        for p in sorted(root.glob(pattern)):
            m = _DATE_RE.search(p.stem)
            if since and (not m or m.group(1) < since):
                continue
            out.append(p)
    return out


def mint_from_docs(repo_root: Path | str, *, since: str | None = None, cap: int = MINT_CAP,
                   wall: Wall | None = None, dry_run: bool = False,
                   net: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mint one probe per NEW design/arming doc, stamping ``expected_now`` from a live route.

    The stamp is measured, never assumed: a probe minted as ``pass`` because the doc really is
    reachable today turns any later miss into a REGRESSION the close catches, and one minted
    ``fail`` records the measured starting state of a thread that cannot yet be reached. Bounded
    by ``cap`` (each stamp costs a real route); a clipped remainder is NAMED, never dropped.

    ``net``, as in :func:`score_threads`: the close runs both in one step against one network, and
    handing the same OBJECT to both is also what lets the router's basis memo hold across them.
    """
    doc = load_probes(repo_root) or {"probes": []}
    known = {p.get("id") for p in doc.get("probes") or []}
    since = since or doc.get("minted_through")
    candidates = [p for p in mint_candidates(repo_root, since=since)
                  if probe_id_for(p) not in known]
    clipped = [p.name for p in candidates[cap:]]
    minted: list[dict[str, Any]] = []
    wall = wall if wall is not None else Wall(None)
    router: Any = None
    if net is not None:
        from laplace.representation import embed_router
        router = embed_router
    for path in candidates[:cap]:
        _dm = _DATE_RE.search(path.stem)
        probe = {
            "id": probe_id_for(path),
            "query": title_terms(path),
            "must_reach": [path.name],
            "top_k": 5,
            "expected_now": "fail",
            "minted": time.strftime("%Y-%m-%d"),
            "doc_date": _dm.group(1) if _dm else None,  # the watermark's honest source
            "why": f"minted mechanically from {path.name} (its own title terms) - the close's "
                   f"standing question: can this thread be reached by the router that must find it",
        }
        # Stamp expected_now from the live router, unless the wall (or a dry run) says no - an
        # unstamped mint defaults to "fail", the conservative side: it can only ever CLEAR.
        floor = THREAD_ROUTE_FLOOR_S if net is not None else THREAD_LOAD_FLOOR_S
        if not dry_run and wall.affords(floor):
            try:
                if net is None:  # once, not per probe - the load is the expensive half
                    from laplace.engine import conceptric
                    from laplace.representation import embed_router
                    net, router = conceptric.load_network(Path(repo_root)), embed_router
                r = router.route(Path(repo_root), net, probe["query"], limit=probe["top_k"])
                files = list(((r or {}).get("files") or []))[:probe["top_k"]]
                if r is not None and _reach(files, probe["must_reach"]):
                    probe["expected_now"] = "pass"
                probe["stamped"] = "live route" if r is not None else "unstamped (no backend)"
            except Exception as exc:  # noqa: BLE001 - an unstampable mint is still a mint
                probe["stamped"] = f"unstamped ({type(exc).__name__})"
        else:
            probe["stamped"] = "unstamped (dry run)" if dry_run else "unstamped (budget)"
        minted.append(probe)
    result = {"candidates": len(candidates), "minted": [p["id"] for p in minted],
              "queries": {p["id"]: p["query"] for p in minted},
              "clipped": clipped, "since": since}
    if minted and not dry_run:
        bank_probes(repo_root, doc.get("session") or "mint", minted)
        fresh = load_probes(repo_root) or {}
        # The watermark is the newest doc date actually CONSUMED, never the wall
        # clock: stamping today across a midnight close would set the mark past
        # the clipped remainder and silently orphan it (found live 2026-08-20,
        # the wants-step build; the remainder is NAMED, never dropped).
        consumed = [p.get("doc_date") for p in minted if p.get("doc_date")]
        fresh["minted_through"] = max(consumed) if consumed else fresh.get("minted_through") or time.strftime("%Y-%m-%d")
        save_probes(repo_root, fresh)
    return result
