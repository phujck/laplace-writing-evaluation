"""sequence_exec.py — the sequence bench: sandboxed execution, byte-compare, typed residue.

A candidate is a *generator program*: source text that, run once, prints the
sequence it claims to generate. This module is the only place the engine
executes model-written code, so the containment is explicit rather than
inherited — nothing in the repo executed generated code before this file
(no ``exec``/``eval`` of generated source anywhere; every ``ast.parse`` site is
static reading).

The containment, in order of what it defends against:

  * ``[sys.executable, "-I", "-S", script]`` — never ``shell=True``. Isolated
    mode drops ``PYTHON*`` env vars, user site-packages and (3.11+) the script
    directory from ``sys.path``; ``-S`` drops site-packages, so the candidate
    cannot import the engine even though the engine spawned it.
  * a FRESH temp directory as ``cwd``, deleted after the run — a candidate that
    writes files writes them nowhere durable.
  * a scrubbed ``env`` — the parent's environment (tokens, ``LAPLACE_*`` state
    paths, proxy credentials) is not inherited.
  * a wall-clock ``timeout`` (:data:`EXEC_TIMEOUT_S`), with POSIX-guarded
    ``setrlimit`` under it as the CPU/address-space/file-size backstop. The
    rlimit clamp is POSIX-only by construction and the byte-compare stays
    correct without it — the author's local box is Windows.
  * bounded output carrying an explicit truncation MARKER, never a silent
    slice, so a short answer is distinguishable from a chopped one.

The gate is byte-equality of :func:`normalize_answer` over the candidate's
stdout against the target literal — the sequence with commas and no spaces, the
answer as stored (the separator is load-bearing: nBDM is taken over the 8-bit
ASCII expansion of that literal). On divergence the bench emits a TYPED residue
record: the first divergent index plus a class from a CLOSED set fixed before
any arm runs (:data:`RESIDUE_CLASSES`).

The anti-vacuity rule is the load-bearing one: a candidate whose execution
produced no trace — timeout, sandbox error, empty stdout — FAILS the gate. Zero
divergences with no output is the exact shape of a false verified.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

# --------------------------------------------------------------------------- #
# Bounds — every one a named constant, none inline
# --------------------------------------------------------------------------- #

#: Per-candidate wall-clock budget, seconds. Deliberately an order of magnitude
#: below every other timeout in the engine (the ladder is 30/60/90/120/180/
#: 300/600s): a sequence generator that has not printed in this long is not
#: slow, it is wrong, and the loop runs thousands of these.
EXEC_TIMEOUT_S: float = 8.0

#: Address-space ceiling for the child (POSIX only). Python 3.11 starts in well
#: under this with ``-S``; a candidate that allocates past it dies as a crash
#: rather than taking the host down.
MEM_LIMIT_BYTES: int = 512 * 1024 * 1024

#: Largest file the child may create (POSIX only) — a candidate that writes
#: instead of printing cannot fill the disk.
FSIZE_LIMIT_BYTES: int = 8 * 1024 * 1024

#: Open-file ceiling for the child (POSIX only).
NOFILE_LIMIT: int = 64

#: stdout is bounded from the HEAD, not the tail: the answer is the head, and a
#: chopped answer must FAIL the byte-compare. The appended marker guarantees
#: inequality even in the pathological case where the head alone would match.
STDOUT_LIMIT: int = 20_000

#: stderr is bounded from the TAIL — the traceback's last frames are the
#: diagnostic — with the marker PREFIXED, the convention verify.py established.
STDERR_TAIL_LIMIT: int = 2_000

TRUNCATION_MARKER: str = "...[truncated]..."

#: The CLOSED residue set. Frozen before any arm runs: a class added later
#: changes what the ledger means, so additions are a preregistration change,
#: not a code change.
RESIDUE_CLASSES: tuple[str, ...] = (
    "off-by-index",   # the terms are right, the indexing is shifted
    "wrong-tail",     # a prefix agrees and the remainder does not (the residual class)
    "parity-flip",    # binary alphabet, every term complemented
    "scale",          # every term a constant multiple of the target
    "no-output",      # ran, printed nothing — the anti-vacuity failure
    "timeout",        # exceeded the wall clock
    "crash",          # non-zero exit, or the sandbox refused to run it
)

#: Ported from ``check_residue.py``: residue records the loop's own synthesis
#: keys, so a residue row can never smuggle a theory back into the loop.
FORBIDDEN_RESIDUE_KEYS: frozenset[str] = frozenset(
    {"thesis", "architecture", "theory", "synthesis"})

#: Per-round row cap, also ported from ``check_residue.py``.
MAX_RESIDUE_ROWS: int = 8

#: Largest shift the off-by-index search considers. Two reasons, both binding:
#: an indexing bug is a small offset (a loop started at 1, a term consumed
#: early), not an arbitrary realignment; and an unbounded search is O(n²) over
#: the term count, which a 20k-term runaway output would turn into a hang
#: inside the organ that exists to stop hangs.
MAX_INDEX_SHIFT: int = 16

_COMMENT_RE = re.compile(r"#[^\n]*")
_WS_RUN_RE = re.compile(r"\s+")
_COMMA_WS_RE = re.compile(r"\s*,\s*")


# --------------------------------------------------------------------------- #
# Answer normalization — shared law for every arm (DESIGN_2026-08-04 §5)
# --------------------------------------------------------------------------- #


def normalize_answer(text: str | None) -> str:
    """Canonicalize an answer string. ONE convention, applied identically to
    every arm and to the published answers, stated in the paper.

    Three steps, in order:

      1. strip comments — ``#`` to end of line. ``//`` is deliberately NOT
         treated as a comment opener: it is floor division, and a formula answer
         like ``a(n)=n//2`` would be destroyed by a C-style comment rule.
      2. collapse every whitespace run (including newlines) to one space and
         strip the ends — whitespace is non-semantic in a sequence literal and
         around formula operators.
      3. canonicalize the separator: no space either side of a comma. This is
         the stored convention — the sequence with commas, no spaces — and it
         is load-bearing downstream, since nBDM is taken over the 8-bit ASCII
         expansion of exactly this string.

    Idempotent: ``normalize_answer(normalize_answer(s)) == normalize_answer(s)``.

    Unwrapping decoration an arm wrapped its answer in (markdown fences, a
    ``Answer:`` preamble) belongs to that arm's answer EXTRACTOR, not here — a
    normalizer that guesses at structure is a normalizer that scores arms
    differently.
    """
    if not text:
        return ""
    s = _COMMENT_RE.sub("", text)
    s = _WS_RUN_RE.sub(" ", s).strip()
    return _COMMA_WS_RE.sub(",", s)


def parse_sequence(literal: str | None) -> list[str]:
    """Split a normalized sequence literal into its terms. The empty string is
    zero terms, never one empty term — the distinction is what makes the
    anti-vacuity rule mechanical."""
    norm = normalize_answer(literal)
    if not norm:
        return []
    return norm.split(",")


def format_sequence(terms: Sequence[Any]) -> str:
    """Render terms in the stored convention: commas, no spaces."""
    return ",".join(str(t).strip() for t in terms)


# --------------------------------------------------------------------------- #
# The sandbox
# --------------------------------------------------------------------------- #


def _bounded_stdout_head(out: str | None) -> tuple[str, bool]:
    """Head of stdout capped at :data:`STDOUT_LIMIT`, marker APPENDED when cut."""
    if not out:
        return "", False
    if len(out) <= STDOUT_LIMIT:
        return out, False
    return out[:STDOUT_LIMIT] + TRUNCATION_MARKER, True


def _bounded_stderr_tail(err: str | None) -> tuple[str, bool]:
    """Tail of stderr capped at :data:`STDERR_TAIL_LIMIT`, marker PREFIXED when
    cut — so a reader can tell a short/empty stderr from a chopped one."""
    if not err:
        return "", False
    if len(err) <= STDERR_TAIL_LIMIT:
        return err, False
    return TRUNCATION_MARKER + err[-STDERR_TAIL_LIMIT:], True


def sandbox_env() -> dict[str, str]:
    """The child's whole environment. The parent's is NOT inherited: it carries
    ``LAPLACE_*`` state paths, proxy credentials and API tokens, none of which a
    candidate has any business reading. ``PYTHON*`` vars would be dropped by
    ``-I`` anyway; they are not set here either way.

    On Windows a bare-``PATH`` environment is not enough for the interpreter to
    start, so the documented minimum (``SYSTEMROOT``/``COMSPEC``/``PATHEXT``) is
    passed through when present."""
    env = {"PATH": os.defpath, "LAPLACE_SANDBOX": "1"}
    if sys.platform == "win32":  # pragma: no cover - POSIX CI
        for key in ("SYSTEMROOT", "SystemRoot", "COMSPEC", "PATHEXT", "TEMP", "TMP"):
            val = os.environ.get(key)
            if val:
                env[key] = val
    return env


def _rlimit_preexec(timeout: float):
    """Return a ``preexec_fn`` applying the rlimit clamp, or ``None`` where the
    platform has no ``resource`` module (Windows).

    Each limit is applied defensively: a platform that refuses one (RLIMIT_AS is
    not honoured everywhere, RLIMIT_NPROC does not exist on every POSIX) must
    not turn into a child that never starts — the wall-clock timeout and the
    byte-compare are correct without any of them.

    ``preexec_fn`` runs after fork and before exec, so it must touch nothing but
    the limits; it is documented-unsafe in a threaded parent, which is why the
    bench is called from the loop's single thread."""
    if sys.platform == "win32":  # pragma: no cover - POSIX CI
        return None
    try:
        import resource
    except ImportError:  # pragma: no cover - POSIX always has it
        return None

    cpu_s = max(1, int(timeout) + 1)  # CPU is the backstop UNDER the wall clock

    def _apply() -> None:  # pragma: no cover - runs in the forked child
        for what, limit in (
            (resource.RLIMIT_CPU, (cpu_s, cpu_s + 1)),
            (resource.RLIMIT_AS, (MEM_LIMIT_BYTES, MEM_LIMIT_BYTES)),
            (resource.RLIMIT_FSIZE, (FSIZE_LIMIT_BYTES, FSIZE_LIMIT_BYTES)),
            (resource.RLIMIT_NOFILE, (NOFILE_LIMIT, NOFILE_LIMIT)),
            (getattr(resource, "RLIMIT_NPROC", None), (0, 0)),
        ):
            if what is None:
                continue
            try:
                resource.setrlimit(what, limit)
            except (ValueError, OSError):
                pass

    return _apply


@dataclass(frozen=True)
class ExecResult:
    """One candidate execution. ``ok`` means the process RAN and exited 0 — it
    says nothing about the answer being right, and nothing about there being an
    answer at all."""

    ok: bool
    returncode: int | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool
    error: str
    duration_s: float

    def as_record(self) -> dict[str, Any]:
        """Ledger projection: bounded stderr only, never the whole stream."""
        return {
            "ok": self.ok,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "stderr_tail": self.stderr,
            "error": self.error,
            "duration_s": round(self.duration_s, 4),
        }


def run_candidate(
    source: str,
    *,
    timeout: float = EXEC_TIMEOUT_S,
    workdir: str | Path | None = None,
) -> ExecResult:
    """Execute one candidate generator program and return its bounded trace.

    ``source`` is written to ``candidate.py`` inside a fresh temp directory (or
    ``workdir`` when the caller wants to inspect the leavings) and run there.
    Never raises for anything the candidate does: a timeout, a crash and a
    sandbox refusal are all ExecResults, because the loop must be able to bank a
    residue for every one of them."""
    if workdir is None:
        with tempfile.TemporaryDirectory(prefix="superarc-exec-") as tmp:
            return _run_in(source, Path(tmp), timeout)
    d = Path(workdir)
    d.mkdir(parents=True, exist_ok=True)
    return _run_in(source, d, timeout)


def _run_in(source: str, d: Path, timeout: float) -> ExecResult:
    script = d / "candidate.py"
    started = time.monotonic()
    try:
        script.write_text(source, encoding="utf-8")
    except OSError as e:
        return ExecResult(False, None, "", "", False, False, False,
                          f"{type(e).__name__}: {e}", time.monotonic() - started)
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-S", script.name],
            cwd=str(d),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=sandbox_env(),
            preexec_fn=_rlimit_preexec(timeout),
        )
    except subprocess.TimeoutExpired as e:
        # The child is already killed by run(); keep whatever it managed to
        # print, so a partially-correct infinite loop still yields a residue.
        out, out_cut = _bounded_stdout_head(_as_text(e.stdout))
        err, err_cut = _bounded_stderr_tail(_as_text(e.stderr))
        return ExecResult(False, None, out, err, out_cut, err_cut, True,
                          f"TimeoutExpired: {timeout}s", time.monotonic() - started)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return ExecResult(False, None, "", "", False, False, False,
                          f"{type(e).__name__}: {e}", time.monotonic() - started)
    out, out_cut = _bounded_stdout_head(proc.stdout)
    err, err_cut = _bounded_stderr_tail(proc.stderr)
    return ExecResult(proc.returncode == 0, proc.returncode, out, err,
                      out_cut, err_cut, False, "", time.monotonic() - started)


def _as_text(blob: Any) -> str:
    if blob is None:
        return ""
    if isinstance(blob, bytes):
        return blob.decode("utf-8", "replace")
    return str(blob)


# --------------------------------------------------------------------------- #
# Typed residue
# --------------------------------------------------------------------------- #


def _first_divergence(got: list[str], expected: list[str]) -> int | None:
    """Index of the first term that differs, or the length of the shorter list
    when one runs out. ``None`` only when the two are identical."""
    for i in range(min(len(got), len(expected))):
        if got[i] != expected[i]:
            return i
    if len(got) != len(expected):
        return min(len(got), len(expected))
    return None


def _shift_of(got: list[str], expected: list[str]) -> int | None:
    """Smallest non-zero shift ``s`` under which the outputs coincide, or None.

    ``s > 0``: the candidate started ``s`` terms LATE (``got[i] == expected[i+s]``).
    ``s < 0``: it started ``|s|`` terms EARLY. At least two overlapping terms are
    required — a one-term coincidence is not evidence of an indexing bug, and
    the search is capped at :data:`MAX_INDEX_SHIFT`."""
    n = min(len(got), len(expected))
    for s in range(1, min(max(n, 1), MAX_INDEX_SHIFT + 1)):
        span = min(len(got), len(expected) - s)
        if span >= 2 and all(got[i] == expected[i + s] for i in range(span)):
            return s
        span = min(len(got) - s, len(expected))
        if span >= 2 and all(got[i + s] == expected[i] for i in range(span)):
            return -s
    return None


def _is_prefix_pair(got: list[str], expected: list[str]) -> bool:
    """One list is a prefix of the other — a truncated or over-long output whose
    head agrees completely. Checked BEFORE the shift search because a periodic
    target is self-similar under a shift, and a stopped-early generator would
    otherwise be typed as an indexing bug."""
    n = min(len(got), len(expected))
    return got[:n] == expected[:n]


def _is_parity_flip(got: list[str], expected: list[str]) -> bool:
    """Both binary, same length, EVERY term complemented. A partial flip is a
    wrong tail, not a parity error."""
    if len(got) != len(expected) or len(got) < 2:
        return False
    flip = {"0": "1", "1": "0"}
    if any(t not in flip for t in expected) or any(t not in flip for t in got):
        return False
    return all(got[i] == flip[expected[i]] for i in range(len(got)))


def _scale_factor(got: list[str], expected: list[str]) -> float | None:
    """Constant ``c != 1`` with ``got[i] == c * expected[i]`` for every term, or
    None. Zeros must map to zeros or the factor is not constant. Two terms
    minimum: any single number is a scaling of any other."""
    if len(got) != len(expected) or len(got) < 2:
        return None
    try:
        g = [float(t) for t in got]
        e = [float(t) for t in expected]
    except ValueError:
        return None
    pivot = next((i for i, v in enumerate(e) if v != 0.0), None)
    if pivot is None:
        return None
    c = g[pivot] / e[pivot]
    if math.isclose(c, 1.0, rel_tol=1e-12, abs_tol=1e-12):
        return None
    for i in range(len(e)):
        if e[i] == 0.0:
            if g[i] != 0.0:
                return None
        elif not math.isclose(g[i], c * e[i], rel_tol=1e-12, abs_tol=1e-12):
            return None
    return c


def classify_divergence(got: list[str], expected: list[str]) -> str:
    """Name the divergence between two term lists, from :data:`RESIDUE_CLASSES`.

    Order is load-bearing and fixed: a prefix pair is a wrong tail before it is
    anything else (a periodic target is self-similar under a shift), and an
    indexing shift is checked before a parity flip because on an alternating
    binary sequence the two are the same observation while an indexing bug is
    the failure the loop can act on. ``wrong-tail`` is the RESIDUAL class —
    every divergence that is not one of the named shapes lands there, which is
    what keeps the set closed."""
    if not got:
        return "no-output"
    if _is_prefix_pair(got, expected):
        return "wrong-tail"
    if _shift_of(got, expected) is not None:
        return "off-by-index"
    if _is_parity_flip(got, expected):
        return "parity-flip"
    if _scale_factor(got, expected) is not None:
        return "scale"
    return "wrong-tail"


def residue_record(
    cls: str,
    index: int | None,
    got: list[str],
    expected: list[str],
    detail: str = "",
) -> dict[str, Any]:
    """Build one typed residue row.

    Invariants ported from ``check_residue.py`` and enforced by
    :func:`check_residue_rows`: the class is from the closed set, the index
    actually indexes the EXECUTED output (or equals its length exactly, when the
    output ended early — and then ``got`` is None, never a fabricated term), and
    the expected/got pair is byte-exact rather than a description of the
    difference."""
    if cls not in RESIDUE_CLASSES:
        raise ValueError(f"residue class {cls!r} not in the closed set {RESIDUE_CLASSES}")
    row: dict[str, Any] = {
        "class": cls,
        "index": index,
        "got": got[index] if index is not None and index < len(got) else None,
        "expected": expected[index] if index is not None and index < len(expected) else None,
        "got_len": len(got),
        "expected_len": len(expected),
    }
    if detail:
        row["detail"] = detail
    return row


def check_residue_rows(rows: Sequence[dict[str, Any]]) -> list[str]:
    """Gate a round's residue rows; returns error strings, empty when clean.

    Four checks, all ported: the per-round row cap, the forbidden-key check (so
    residue never smuggles in synthesis), the closed class set, and the index
    invariant — an index that actually indexes the executed output."""
    errs: list[str] = []
    if len(rows) > MAX_RESIDUE_ROWS:
        errs.append(f"{len(rows)} residue rows exceeds cap {MAX_RESIDUE_ROWS}")
    for i, r in enumerate(rows):
        if bad := FORBIDDEN_RESIDUE_KEYS & set(r):
            errs.append(f"residue[{i}]: forbidden synthesis keys: {sorted(bad)}")
        if r.get("class") not in RESIDUE_CLASSES:
            errs.append(f"residue[{i}]: class missing/unknown: {r.get('class')!r}")
        idx, glen = r.get("index"), r.get("got_len")
        if idx is None:
            if r.get("class") not in ("no-output", "timeout", "crash"):
                errs.append(f"residue[{i}]: divergence row with no index")
            continue
        if not isinstance(idx, int) or not isinstance(glen, int):
            errs.append(f"residue[{i}]: index/got_len must be ints")
            continue
        if idx < 0 or idx > glen:
            errs.append(f"residue[{i}]: index {idx} does not index a {glen}-term output")
        elif idx == glen and r.get("got") is not None:
            errs.append(f"residue[{i}]: index {idx} is past the output but carries a term")
        elif idx < glen and r.get("got") is None:
            errs.append(f"residue[{i}]: index {idx} indexes the output but carries no term")
    return errs


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Verdict:
    """The bench's verdict on one candidate. ``passed`` is the gate: the process
    ran, printed something, and its normalized stdout is byte-identical to the
    normalized target."""

    passed: bool
    residue: dict[str, Any] | None
    answer: str
    target: str
    execution: dict[str, Any] = field(default_factory=dict)

    def as_record(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "residue": self.residue,
            "answer": self.answer,
            "target": self.target,
            "execution": self.execution,
        }


def verify_candidate(
    source: str,
    target: str | Sequence[Any],
    *,
    timeout: float = EXEC_TIMEOUT_S,
    workdir: str | Path | None = None,
) -> Verdict:
    """Run a candidate and byte-compare its answer against ``target``.

    ``target`` is the sequence literal (commas, no spaces) or any sequence of
    terms rendered into it. The gate FAILS — with a typed residue, never
    silently — on a timeout, a crash, an empty stdout, or any byte difference.
    Passing requires all three of: process completed, output non-empty, bytes
    equal. Empty output is never a pass, whatever the exit code says."""
    target_str = target if isinstance(target, str) else format_sequence(target)
    expected = parse_sequence(target_str)
    norm_target = format_sequence(expected)

    res = run_candidate(source, timeout=timeout, workdir=workdir)
    answer = normalize_answer(res.stdout)
    got = parse_sequence(answer)
    execution = res.as_record()

    if res.timed_out:
        return Verdict(False, residue_record("timeout", None, got, expected,
                                             detail=res.error), answer, norm_target, execution)
    if not res.ok:
        detail = res.error or f"exit {res.returncode}: {res.stderr[-200:]}"
        return Verdict(False, residue_record("crash", None, got, expected,
                                             detail=detail), answer, norm_target, execution)
    if not got:
        # The anti-vacuity rule: no trace is a FAILURE, not zero divergences.
        return Verdict(False, residue_record("no-output", None, got, expected,
                                             detail="exited 0 with empty stdout"),
                       answer, norm_target, execution)
    if answer == norm_target:
        return Verdict(True, None, answer, norm_target, execution)

    idx = _first_divergence(got, expected)
    if idx is None:
        # Byte-unequal with term-equal parts: only reachable if the two sides
        # were normalized by different rules, which is a bug here, not there.
        idx = min(len(got), len(expected))
    cls = classify_divergence(got, expected)
    detail = ""
    if cls == "off-by-index":
        detail = f"shift {_shift_of(got, expected)}"
    elif cls == "scale":
        detail = f"factor {_scale_factor(got, expected)}"
    return Verdict(False, residue_record(cls, idx, got, expected, detail=detail),
                   answer, norm_target, execution)
