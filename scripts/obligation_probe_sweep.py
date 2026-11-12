#!/usr/bin/env python3
"""obligation_probe_sweep.py — the second close instrument, AP-20's cure.

scripts/ledger_age_audit.py (THE AGING TEETH) answers "is this late?" — it walks the
accumulating ledgers and FAILs an OPEN row past its class's max quiet age with no
dated defer. It cannot answer "is this done?": every one of the 8 fossils AP-02/AP-03
found riding 72 row-days (2026-08-20) sat inside the age audit's defer window or had
no gate at all, so VERDICT=PASS the whole time a probe would have struck them. This
script is the orthogonal second reading — it runs the mechanical DONE-CONDITION each
row now carries and reports what the age audit structurally cannot see.

THE SCHEMA IT READS (AMEND-20260820-acceptance-probe-schema, corpus_friction/
work_orders.jsonl): an obligation row may carry
    {accept: <shell command>, done_means: "pass", on_skip: "UNPROVEN",
     probe_cost: "cheap"|"pytest", strikes: <str, optional>}
across the two obligation ledgers:
    corpus_friction/work_orders.jsonl   (kind: work-order / amendment rows)
    contract/promises.jsonl             (promise / note rows)

VERDICT SPACE IS THREE, NOT TWO (AP-07 / schema law 1) — a probe that can only ever
exit 0-or-not cannot itself distinguish "genuinely still open" from "the named
behaviour SKIPPED on this box" (measured live: two rows exit 0 on a bare pytest
invocation while every behaviour they name skips). So:
    PASS      accept exited 0.
    UNPROVEN  accept exited nonzero AND the row carries on_skip — the schema's own
              escape hatch for exactly this ambiguity; never treated as a strike-
              eligible FAIL, never auto-struck.
    FAIL      accept exited nonzero and the row carries no on_skip escape — genuinely,
              mechanically still open.

THE AP-13 WRAP (schema law 3), applied to every row: `git status --porcelain` is read
before and after each accept command. AP-13 reproduced this LIVE, twice, in the audit
that authored this schema — a pytest-based accept can rewrite a corpus_network sidecar
(``*.paragraph_plan.N<k>.json`` under synthetics papers) as a side effect, and which
N-file gets touched is NOT stable across runs (N1, N2, N4 all separately observed) — so
a hard-coded restore path list under-restores. This sweep restores by PATTERN, never
by a fixed list: any newly-dirtied path matching the sidecar-regeneration class
(_SIDECAR_RESTORE_RE below) is `git checkout --`ed back automatically, because that
class is a pure re-timestamp with no content loss (verified by hand this session — the
only byte that changes is the cached ``ts`` field). Anything else that goes newly
dirty is left exactly where it sits and is REPORTED, never restored: the schema
amendment names a live incident (this lane's own sweep runs picked up sibling-lane
writes to diagrams/atlas_index.json, scripts/standup.sh, src/laplace/engine/close_beats.py,
src/laplace/gitio.py mid-flight under concurrent fixer lanes) — a blind whole-tree
restore in that regime destroys someone else's real work. The class-pattern restore
is deliberately narrow so it can never reach a sibling lane's file.

REPORT-ONLY, ALWAYS: this script never writes to either ledger and never strikes a
row off anything. Every "proposed strike-off" below is exactly that — a proposal —
and goes through the evidence door by hand (AP-01's own risk note: "strike-offs go
through the evidence door, never auto-applied"). A row that DECLARES a ``strikes``
exemption is never proposed regardless of verdict; the field's semantics are DEFINED
once, in the schema module where every reader gets them — ``engine_ledger.strikes_exempt``
/ ``engine_ledger.STRIKES_EXEMPLAR`` (WO-20260820-ledger-semantics-hardening cure b) —
and this script asks that function rather than restating the rule. ``strikes`` is read,
never written, here.

PROBE STRENGTH (WO-20260820-probe-strength-declaration): every probed row is
classified into one of three strength classes from its own ``accept`` command,
mechanically, via ``classify_probe_strength`` below —
    porcelain  the command only checks presence (``test -f`` / bare ``grep`` for a
               marker or the row's own text) — proves the row was TOUCHED, never
               that the cure landed.
    content    the command parses a store or source file and asserts a VALUE inside
               it (a ``python -c`` reading JSON, or a targeted grep for a specific
               produced value) — proves the artefact carries the right content.
    behavior   the command imports project code and CALLS it, or runs pytest —
               proves the code path actually executes as claimed.
A PASS on a porcelain probe is NEVER proposed for strike-off, full stop — porcelain
proves presence, not cure (the live incident this WO names: WO-20260820-kmeans-is-
the-new-bottleneck's original probe was ``test -f gate_task1.json && grep kmeans
work_orders.jsonl``, which passed the day the named cure was definitively not
landed). ``strength`` is rendered beside every verdict in both the text and JSON
report.

EFFECTIVE STATUS (WO-20260820-ledger-semantics-hardening, cure a): the report also
carries each row's status alongside its EFFECTIVE status, computed by the ONE join
helper (``src.laplace.engine_ledger``) from the RES-row join — a row's stored
``status`` field is raise-time-only and can read ``open`` long after some resolution
row's ``consumes`` has closed it out. ``effective_status`` differing from the row's
stored ``status`` is flagged so a reader never has to redo that archaeology by hand.

CLI:
    obligation_probe_sweep.py                  # full sweep (cheap + pytest tier), text report
    obligation_probe_sweep.py --cheap-only      # skip probe_cost == "pytest" rows (the
                                                 # close-time tier — AP-20's own risk note:
                                                 # "gate expensive probes ... run only the
                                                 # cheap tier every close, the full tier at
                                                 # campaign boundaries")
    obligation_probe_sweep.py --json            # machine-readable report on stdout only
    obligation_probe_sweep.py --repo PATH       # repo root (default: this script's parent's parent)
    obligation_probe_sweep.py --timeout N       # per-probe subprocess timeout, seconds (default 180)

Exit code is always 0 — this is a REPORT, not a gate (see module docstring; a future
promotion to FAIL_ELIGIBLE is a decision for a later close, per AP-20's own finding).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# repo/scripts/obligation_probe_sweep.py -> repo/src on sys.path, so the join helper
# imports the same way whether this script is run in place or from another cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from laplace.engine import engine_ledger  # noqa: E402
from laplace.core.records.rows import load_records  # noqa: E402

LEDGERS = ("corpus_friction/work_orders.jsonl", "contract/promises.jsonl")

#: PROBE STRENGTH classification (see module docstring). Deliberately mechanical and
#: conservative: a command this classifier cannot confidently place as "porcelain" or
#: "behavior" is called "content", never silently upgraded to a stronger class than it
#: has earned.
_PORCELAIN_CLAUSE_RE = re.compile(r"^(test -f\b|grep\b)")
#: `pytest` as its OWN shell token only — surrounded by whitespace/string-edges, never
#: merely `\bpytest\b`, which also matches inside a path segment like a pytest tmp_path
#: fixture's own `.../pytest-433/...` (word boundary treats `-` as a break; whitespace
#: boundary does not). A probe naming such a path in its accept command must not be
#: misread as itself running pytest.
_PYTEST_RE = re.compile(r"(?<!\S)pytest(?!\S)")
_PYTHON_DASH_C_RE = re.compile(r"python\S*\s+-c\b")
_PROJECT_IMPORT_RE = re.compile(
    r"sys\.path\.insert\(0,\s*['\"](?:src|scripts)['\"]\)|\bfrom\s+laplace\b|\bimport\s+laplace\b"
)
#: `alias.attr(` calls that don't count as "executing a code path" on their own —
#: stdlib plumbing every content-tier probe also uses to read a file and compare it.
_INERT_CALL_PREFIXES = ("sys.", "json.", "re.", "os.", "pathlib.")


def classify_probe_strength(accept: str) -> str:
    """porcelain | content | behavior, from the ``accept`` command text alone —
    see the module docstring's PROBE STRENGTH section for the rule and rationale."""
    cmd = accept.strip()
    if _PYTEST_RE.search(cmd):
        return "behavior"
    if _PYTHON_DASH_C_RE.search(cmd):
        if _PROJECT_IMPORT_RE.search(cmd):
            calls = re.findall(r"\b([\w.]+)\.(\w+)\(", cmd)
            executing = [(m, a) for m, a in calls
                         if not (m + ".").startswith(_INERT_CALL_PREFIXES)]
            if executing:
                return "behavior"
        return "content"
    parts = [p.strip() for p in re.split(r"&&|\|\||;", cmd) if p.strip()]
    if parts and all(_PORCELAIN_CLAUSE_RE.match(p) for p in parts):
        return "porcelain"
    return "content"

#: the known sidecar-regeneration class (AP-13) — the ONLY class of newly-dirtied path
#: this sweep will `git checkout --` on its own. Deliberately a CLASS pattern, never a
#: fixed filename list (the verifier's binding objection to the original cure text: three
#: different N-files were seen dirtied across different runs; a named list under-restores
#: whichever one wasn't anticipated).
_SIDECAR_RESTORE_RE = re.compile(r"_form_retrieval\.paragraph_plan\.N\d+\.json$")


@dataclass
class ProbeRow:
    id: str
    source: str
    record: Optional[str]
    accept: str
    done_means: str
    on_skip: Optional[str]
    probe_cost: str
    strikes: Optional[str]
    kind: Optional[str]
    stored_status: str
    strength: str


@dataclass
class ProbeResult:
    row: ProbeRow
    rc: Optional[int]
    verdict: str  # PASS | FAIL | UNPROVEN | ERROR
    duration_s: float
    stdout_tail: str
    stderr_tail: str
    effective_status: str = ""
    status_reason: str = "stored"
    restored: list[str] = field(default_factory=list)
    left_dirty: list[str] = field(default_factory=list)
    proposed_strike_off: bool = False
    skipped_tier: bool = False


def load_rows(repo: Path) -> tuple[list[ProbeRow], dict[str, dict]]:
    """(rows carrying the acceptance-probe schema's ``accept`` key, the RES-row
    consumption index built from EVERY row in both ledgers — the index needs the
    full ledger, not just the accept-carrying subset, since a resolution row never
    itself carries ``accept``)."""
    rows: list[ProbeRow] = []
    all_records: list[dict] = []
    for rel in LEDGERS:
        recs = load_records(repo / rel)
        all_records.extend(recs)
        for rec in recs:
            if "accept" not in rec:
                continue
            rows.append(ProbeRow(
                id=str(rec.get("id", "?")),
                source=rel,
                record=rec.get("record"),
                accept=str(rec["accept"]),
                done_means=str(rec.get("done_means", "pass")),
                on_skip=rec.get("on_skip"),
                probe_cost=str(rec.get("probe_cost", "cheap")),
                strikes=engine_ledger.row_strikes(rec),
                kind=engine_ledger.row_kind(rec),
                stored_status=str(rec.get("status", "open")),
                strength=classify_probe_strength(str(rec["accept"])),
            ))
    index = engine_ledger.build_consumption_index(all_records)
    return rows, index


def _git_status(repo: Path) -> dict[str, str]:
    """path -> XY status code, via `git status --porcelain -z` (NUL-separated, unquoted
    paths — robust against spaces/unicode, unlike the human `--porcelain` form)."""
    proc = subprocess.run(["git", "status", "--porcelain", "-z"], cwd=str(repo),
                           capture_output=True, text=True, timeout=30)
    tokens = proc.stdout.split("\0")
    out: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok:
            i += 1
            continue
        xy, path = tok[:2], tok[3:]
        out[path] = xy
        # a rename/copy entry carries a SECOND NUL-separated token (the origin path) —
        # consume and drop it so it is never mistaken for an independent dirtied path.
        if xy[0] in ("R", "C"):
            i += 1
        i += 1
    return out


def _run_accept(repo: Path, accept: str, timeout: int) -> tuple[Optional[int], str, str]:
    try:
        proc = subprocess.run(
            ["bash", "-c", accept], cwd=str(repo), capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        return None, exc.stdout or "", f"TIMEOUT after {timeout}s"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "", str(exc)


def run_sweep(repo: Path, cheap_only: bool, timeout: int) -> list[ProbeResult]:
    rows, index = load_rows(repo)
    results: list[ProbeResult] = []
    for row in rows:
        eff_status, status_reason = engine_ledger.effective_status(
            row.id, row.stored_status, index)
        if cheap_only and row.probe_cost == "pytest":
            results.append(ProbeResult(
                row=row, rc=None, verdict="SKIPPED-TIER", duration_s=0.0,
                stdout_tail="", stderr_tail="",
                effective_status=eff_status, status_reason=status_reason,
                skipped_tier=True,
            ))
            continue

        before = _git_status(repo)
        t0 = time.monotonic()
        rc, out, err = _run_accept(repo, row.accept, timeout)
        dt = time.monotonic() - t0
        after = _git_status(repo)

        newly_dirtied = [p for p in after if p not in before]
        restored: list[str] = []
        left_dirty: list[str] = []
        for p in newly_dirtied:
            if _SIDECAR_RESTORE_RE.search(p):
                chk = subprocess.run(["git", "checkout", "--", p], cwd=str(repo),
                                      capture_output=True, text=True, timeout=30)
                if chk.returncode == 0:
                    restored.append(p)
                else:
                    left_dirty.append(p)  # restore attempt itself failed — report honestly
            else:
                left_dirty.append(p)

        if rc is None:
            verdict = "ERROR"
        elif rc == 0:
            verdict = "PASS"
        elif row.on_skip:
            verdict = "UNPROVEN"
        else:
            verdict = "FAIL"

        # WO-20260820-probe-strength-declaration: a porcelain PASS is NEVER proposed
        # for strike-off — porcelain proves presence, not cure — regardless of
        # `strikes`, which governs a different exemption (the relational half).
        proposed = verdict == "PASS" and not row.strikes and row.strength != "porcelain"

        results.append(ProbeResult(
            row=row, rc=rc, verdict=verdict, duration_s=round(dt, 2),
            stdout_tail=out.strip()[-300:], stderr_tail=err.strip()[-300:],
            effective_status=eff_status, status_reason=status_reason,
            restored=restored, left_dirty=left_dirty, proposed_strike_off=proposed,
        ))
    return results


def to_report(results: list[ProbeResult], cheap_only: bool) -> dict:
    ran = [r for r in results if not r.skipped_tier]
    n_pass = sum(1 for r in ran if r.verdict == "PASS")
    n_fail = sum(1 for r in ran if r.verdict == "FAIL")
    n_unproven = sum(1 for r in ran if r.verdict == "UNPROVEN")
    n_error = sum(1 for r in ran if r.verdict == "ERROR")
    n_skipped_tier = sum(1 for r in results if r.skipped_tier)
    proposed = [r.row.id for r in ran if r.proposed_strike_off]
    left_dirty = sorted({p for r in ran for p in r.left_dirty})
    restored = sorted({p for r in ran for p in r.restored})
    n_porcelain = sum(1 for r in ran if r.row.strength == "porcelain")
    n_content = sum(1 for r in ran if r.row.strength == "content")
    n_behavior = sum(1 for r in ran if r.row.strength == "behavior")
    porcelain_pass_withheld = [
        r.row.id for r in ran
        if r.verdict == "PASS" and r.row.strength == "porcelain" and not r.row.strikes
    ]
    status_drifted = [r.row.id for r in ran if r.effective_status != r.row.stored_status]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "cheap-only" if cheap_only else "full",
        "ledgers": list(LEDGERS),
        "rows": [
            {
                "id": r.row.id,
                "source": r.row.source,
                "record": r.row.record,
                "kind": r.row.kind,
                "accept": r.row.accept,
                "done_means": r.row.done_means,
                "on_skip": r.row.on_skip,
                "probe_cost": r.row.probe_cost,
                "strength": r.row.strength,
                "strikes": r.row.strikes,
                "rc": r.rc,
                "verdict": r.verdict,
                "duration_s": r.duration_s,
                "stdout_tail": r.stdout_tail,
                "stderr_tail": r.stderr_tail,
                "stored_status": r.row.stored_status,
                "effective_status": r.effective_status,
                "status_reason": r.status_reason,
                "status_drifted": (r.effective_status != r.row.stored_status),
                "tree_restored": r.restored,
                "tree_left_dirty": r.left_dirty,
                "proposed_strike_off": r.proposed_strike_off,
            }
            for r in results
        ],
        "summary": {
            "total_rows": len(results),
            "ran": len(ran),
            "skipped_tier": n_skipped_tier,
            "pass": n_pass,
            "fail": n_fail,
            "unproven": n_unproven,
            "error": n_error,
            "porcelain": n_porcelain,
            "content": n_content,
            "behavior": n_behavior,
            "porcelain_pass_withheld_from_strike_off": porcelain_pass_withheld,
            "status_drifted_from_stored": status_drifted,
            "proposed_strike_offs": proposed,
            "tree_restored": restored,
            "tree_left_dirty_for_operator": left_dirty,
            "note": ("report-only — proposed strike-offs go through the evidence door "
                     "by hand, never auto-applied; tree_left_dirty_for_operator names any "
                     "path a probe dirtied outside the known sidecar-regeneration class, "
                     "which this sweep deliberately never touches (could be a sibling "
                     "lane's real work under concurrent fixer runs); a porcelain PASS is "
                     "never proposed for strike-off regardless of verdict — see "
                     "porcelain_pass_withheld_from_strike_off; status_drifted_from_stored "
                     "names rows whose RES-row-joined effective status disagrees with "
                     "their own stored status field"),
        },
    }


def print_text_report(report: dict) -> None:
    for row in report["rows"]:
        if row["verdict"] == "SKIPPED-TIER":
            print(f"SKIPPED-TIER {row['id']} (probe_cost=pytest, --cheap-only)")
            continue
        flags = []
        if row["tree_restored"]:
            flags.append(f"restored:{row['tree_restored']}")
        if row["tree_left_dirty"]:
            flags.append(f"LEFT-DIRTY:{row['tree_left_dirty']}")
        strike = " [strike-off candidate]" if row["proposed_strike_off"] else ""
        if row["verdict"] == "PASS" and row["strength"] == "porcelain" and not row["strikes"]:
            strike = " [porcelain PASS — strike-off withheld]"
        drift = f" STATUS-DRIFT:{row['stored_status']}->{row['effective_status']}" \
            if row["status_drifted"] else ""
        tail = f" {' '.join(flags)}" if flags else ""
        print(f"{row['verdict']:<9} {row['id']} [{row['strength']}] "
              f"(rc={row['rc']}, {row['duration_s']}s)"
              f"{strike}{drift}{tail}")
    s = report["summary"]
    print()
    print(f"VERDICT=PASS pass={s['pass']} fail={s['fail']} unproven={s['unproven']} "
          f"error={s['error']} skipped_tier={s['skipped_tier']} "
          f"strength(porcelain={s['porcelain']},content={s['content']},"
          f"behavior={s['behavior']}) "
          f"proposed_strikes={len(s['proposed_strike_offs'])} "
          f"porcelain_withheld={len(s['porcelain_pass_withheld_from_strike_off'])} "
          f"status_drifted={len(s['status_drifted_from_stored'])} "
          f"left_dirty={len(s['tree_left_dirty_for_operator'])}")
    if s["proposed_strike_offs"]:
        print(f"proposed strike-offs (evidence door, never auto-applied): "
              f"{', '.join(s['proposed_strike_offs'])}")
    if s["tree_left_dirty_for_operator"]:
        print(f"left dirty for the operator (outside the sidecar-restore class): "
              f"{', '.join(s['tree_left_dirty_for_operator'])}")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent),
                     help="repo root (default: this script's repo)")
    ap.add_argument("--cheap-only", action="store_true",
                     help="skip probe_cost == pytest rows (the close-time tier)")
    ap.add_argument("--json", action="store_true", help="emit JSON only, no text report")
    ap.add_argument("--timeout", type=int, default=180, help="per-probe timeout, seconds")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    results = run_sweep(repo, cheap_only=args.cheap_only, timeout=args.timeout)
    report = to_report(results, cheap_only=args.cheap_only)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_text_report(report)
    return 0  # a report, never a gate — see module docstring


if __name__ == "__main__":
    sys.exit(main())
