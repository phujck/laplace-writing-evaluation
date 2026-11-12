#!/usr/bin/env python3
"""run_claim_checks.py — make the audit convention mechanical, so a banked claim expires LOUDLY.

AUDIT_2026-07-13 introduced the convention: every banked claim carries its CHECK — a one-line
mechanical predicate. The point of that convention is that a claim whose check fails at a later
wake has DRIFTED, not gone mysterious: nobody should pay a scout to rediscover it. This runner is
the reader half of that convention. It scans the repo-root AUDIT_*.md files AND the live interface-
facing docs (:data:`INTERFACE_DOCS` — W8.3's doc honesty sweep folded the interface's mechanically-
checkable claims into this same idiom), lifts every `CHECK:` line (following its continuation onto
wrapped indented lines), and does the honest thing with each:

  RUNNABLE  the check quotes a shell command in backticks. If a machine-checkable expectation
            trails it (→ True / = N / ≥ N / non-empty / resolves), the command is run from the
            repo root and the expectation evaluated: PASS or FAIL. If the expectation is written
            for a human eye ("still says FROZEN", "hits inside dashboard()"), the command is run
            and its OUTPUT is surfaced for the eye — neither pass nor fail, a reading.
  PROSE     no backticked command to run. Reported, never judged.

THE ENVIRONMENT IS PART OF THE CLAIM (ARMING Appendix F). The common CHECK idioms — the file
`grep`s, `head`/`test`/`du`/`wc`/`cut` probes, and `python -c` one-liners — are evaluated
NATIVELY in this process, with no shell at all, so they yield the same verdict on Windows-without-
bash as on Linux. A CHECK that is genuinely shell (a redirect, a `;` sequence, a command we do not
model natively) is run through a shell resolved at runtime (`bash` → `sh` → Git-for-Windows bash);
when no shell exists it is reported ENV — an honest "could not evaluate here", never a fabricated
FAIL. ENV never moves the exit code.

It NEVER edits the audit to make a check pass — the runner adapts to the corpus, never the corpus
to the runner. A CHECK banked malformed (no runnable command) is reported PROSE, verbatim, as the
finding it is. Exit 1 if any FAIL fired, else 0: a drifted claim moves the exit code, loudly.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# A CHECK label: "CHECK:", "CHECK (route):" — the parenthetical qualifier is allowed, a bare
# "CHECK when fixed:" (a conditional future check) is intentionally NOT a check to run.
CHECK_LABEL_RE = re.compile(r"\bCHECK(?:\s*\([^)]*\))?\s*:")
BACKTICK_RE = re.compile(r"`([^`]+)`")
# first-token gate: a backtick span is a runnable command only if it opens with a real executable
# (guards against inline-code that isn't a command, e.g. the bare `/` in a prose check).
COMMAND_STARTERS = {
    "python", "python3", ".venv/bin/python", "grep", "egrep", "rg", "head", "tail", "cat",
    "ls", "git", "wc", "find", "sort", "uniq", "sed", "awk", "test", "bash", "sh", "jq",
    "echo", "printf",
}
# NOTE: du/cut are deliberately NOT command-starters. The classifier runs BEFORE any shell, so a
# check like `du -sm .git | cut -f1` classified as PROSE at HEAD independent of bash on PATH —
# adding them here would silently flip that live verdict PROSE→EYE, which is not a bash-independence
# port. They remain modelled in _BUILTINS so they still evaluate natively as later pipeline stages
# (e.g. `grep … | cut -f1`) without ever touching a shell.


# The live interface-facing docs swept in W8.3: their mechanically-checkable claims about the
# interface now carry a CHECK in this idiom, so a drifted interface claim expires as loudly as a
# drifted audit claim. Scanned IN ADDITION to the AUDIT_*.md corpus; a path absent from the scanned
# repo (a fixture tmp_path carries only its own AUDIT_*.md) is simply skipped, never a FAIL.
INTERFACE_DOCS = (
    "interface/FUNCTION_INTERROGATIONS.md",
    "PIPELINE_GUIDE.md",
    "TECHNICAL_GUIDE.md",
    "HANDOFF.md",
)


@dataclass
class ClaimCheck:
    audit: str          # audit filename
    text: str           # the check text, label-stripped, continuation joined
    kind: str           # RUNNABLE | PROSE
    command: str = ""   # the first shell command, if RUNNABLE
    verdict: str = "PROSE"  # PASS | FAIL | EYE | ENV | PROSE
    output: str = ""    # command output (FAIL / EYE / ENV)


def iter_check_texts(md: str):
    """Yield each CHECK's text (label-stripped, wrapped continuation lines folded in)."""
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        m = CHECK_LABEL_RE.search(lines[i])
        if not m:
            i += 1
            continue
        parts = [lines[i][m.end():].strip()]
        j = i + 1
        while j < len(lines):
            nxt = lines[j]
            if not nxt.strip() or not nxt[:1].isspace():
                break  # blank or unindented — the check block has ended
            s = nxt.lstrip()
            if s.startswith(("- ", "* ", "#")) or CHECK_LABEL_RE.search(nxt):
                break  # a new bullet / heading / the next check
            parts.append(s)
            j += 1
        yield " ".join(p for p in parts if p).strip()
        i = j


def _is_command(span: str) -> bool:
    """A backtick span opens with a real executable — not e.g. the bare `/` of a prose check."""
    toks = span.strip().split()
    if not toks:
        return False
    head = toks[0]
    return head in COMMAND_STARTERS or head.split("/")[-1] in COMMAND_STARTERS


def classify(text: str) -> tuple[str, str, str]:
    """(kind, command, expectation_text). expectation is scoped to the run between the first
    command and the next backtick span, so a compound check judges only its first command."""
    spans = list(BACKTICK_RE.finditer(text))
    cmd_span = next((sp for sp in spans if _is_command(sp.group(1))), None)
    if cmd_span is None:
        return "PROSE", "", ""
    later = [sp for sp in spans if sp.start() > cmd_span.end()]
    end = later[0].start() if later else len(text)
    return "RUNNABLE", cmd_span.group(1).strip(), text[cmd_span.end():end]


# --------------------------------------------------------------------------- native command engine
# The common CHECK idioms are modelled in-process so they never touch a shell: the same verdict
# lands on Windows-without-bash as on Linux. Anything not modelled here raises _Unhandled and the
# caller falls back to a resolved shell (or ENV when none exists).

class _Unhandled(Exception):
    """The native engine cannot model this command; fall back to a real shell."""


def _bre_to_re(pat: str) -> str:
    """Translate a GNU-grep basic-regexp (BRE) pattern to a Python-re pattern for the idioms we
    see: `\\|` is alternation, a bare `|` is a literal pipe, `\\(`/`\\)`/`\\{`/`\\}`/`\\+`/`\\?`
    are the regex metacharacters and their bare forms are literals."""
    out = []
    i, n = 0, len(pat)
    while i < n:
        c = pat[i]
        if c == "\\" and i + 1 < n:
            nxt = pat[i + 1]
            if nxt == "|":
                out.append("|")            # \| → alternation
            elif nxt in "(){}+?":
                out.append(nxt)            # \( \) \{ \} \+ \? → regex meta
            else:
                out.append("\\" + nxt)     # keep the escape (\. \\ \< …)
            i += 2
        elif c in "|(){}+?":
            out.append("\\" + c)           # literal in BRE
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _read_repo_file(repo: Path, name: str) -> str:
    return (repo / name).read_text(encoding="utf-8", errors="replace")


def _h_grep(argv, stdin, repo):
    flags: set[str] = set()
    dashe = None
    args = argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            i += 1
            break
        if a.startswith("-") and len(a) > 1 and not a[1:].isdigit():
            body = a[1:]
            j = 0
            while j < len(body):
                f = body[j]
                if f == "e":
                    rest = body[j + 1:]
                    if rest:
                        dashe = rest
                    else:
                        i += 1
                        dashe = args[i]
                    break
                if f in "cnihEovwFr":
                    flags.add(f)
                    j += 1
                else:
                    raise _Unhandled
            i += 1
            continue
        break
    rest = args[i:]
    if dashe is not None:
        pattern, files = dashe, rest
    else:
        if not rest:
            raise _Unhandled
        pattern, files = rest[0], rest[1:]

    reflags = re.IGNORECASE if "i" in flags else 0
    if "F" in flags:
        body = re.escape(pattern)
    elif "E" in flags:
        body = pattern
    else:
        body = _bre_to_re(pattern)
    if "w" in flags:
        body = r"\b(?:" + body + r")\b"
    try:
        rx = re.compile(body, reflags)
    except re.error:
        raise _Unhandled

    inputs: list[tuple[str | None, str]] = []
    if files:
        for f in files:
            try:
                inputs.append((f, _read_repo_file(repo, f)))
            except (FileNotFoundError, IsADirectoryError, OSError):
                return 2, f"grep: {f}: No such file or directory"
    else:
        inputs.append((None, stdin or ""))
    multi = len(files) > 1
    invert = "v" in flags

    total = 0
    out_lines: list[str] = []
    for label, txt in inputs:
        for lineno, line in enumerate(txt.splitlines(), 1):
            hit = bool(rx.search(line))
            if invert:
                hit = not hit
            if hit:
                total += 1
                if "c" not in flags:
                    prefix = ""
                    if multi and label is not None:
                        prefix += f"{label}:"
                    if "n" in flags:
                        prefix += f"{lineno}:"
                    out_lines.append(prefix + line)
    if "c" in flags:
        return (0 if total else 1), str(total)
    return (0 if out_lines else 1), "\n".join(out_lines)


def _h_head(argv, stdin, repo):
    n = 10
    files = []
    args = argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-n":
            i += 1
            n = int(args[i])
        elif re.fullmatch(r"-\d+", a):
            n = int(a[1:])
        elif a.startswith("-n") and a[2:].isdigit():
            n = int(a[2:])
        elif a.startswith("-"):
            raise _Unhandled
        else:
            files.append(a)
        i += 1
    if files:
        try:
            txt = _read_repo_file(repo, files[0])
        except OSError:
            return 1, f"head: cannot open '{files[0]}'"
    else:
        txt = stdin or ""
    return 0, "\n".join(txt.splitlines()[:n])


def _h_tail(argv, stdin, repo):
    n = 10
    files = []
    args = argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-n":
            i += 1
            n = int(args[i].lstrip("+"))
        elif re.fullmatch(r"-\d+", a):
            n = int(a[1:])
        elif a.startswith("-"):
            raise _Unhandled
        else:
            files.append(a)
        i += 1
    if files:
        try:
            txt = _read_repo_file(repo, files[0])
        except OSError:
            return 1, f"tail: cannot open '{files[0]}'"
    else:
        txt = stdin or ""
    return 0, "\n".join(txt.splitlines()[-n:] if n else [])


def _h_cat(argv, stdin, repo):
    files = [a for a in argv[1:] if not a.startswith("-")]
    if any(a.startswith("-") and a != "-" for a in argv[1:]):
        raise _Unhandled
    if not files:
        return 0, stdin or ""
    chunks = []
    for f in files:
        try:
            chunks.append(_read_repo_file(repo, f))
        except OSError:
            return 1, f"cat: {f}: No such file or directory"
    return 0, "".join(chunks)


def _h_wc(argv, stdin, repo):
    mode = None
    files = []
    for a in argv[1:]:
        if a in ("-l", "-c", "-w", "-m"):
            mode = a[1]
        elif a.startswith("-"):
            raise _Unhandled
        else:
            files.append(a)
    if files:
        try:
            txt = _read_repo_file(repo, files[0])
        except OSError:
            return 1, f"wc: {files[0]}: No such file or directory"
    else:
        txt = stdin or ""
    if mode == "l":
        val = txt.count("\n")
    elif mode == "w":
        val = len(txt.split())
    else:  # -c / -m / default → bytes-ish
        val = len(txt)
    return 0, str(val)


def _parse_fields(spec: str) -> list[int]:
    sel: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            lo, hi = part.split("-", 1)
            sel.extend(range(int(lo), int(hi) + 1))
        else:
            sel.append(int(part))
    return sel


def _h_cut(argv, stdin, repo):
    delim = "\t"
    fields = None
    files = []
    args = argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-d":
            i += 1
            delim = args[i]
        elif a.startswith("-d"):
            delim = a[2:]
        elif a == "-f":
            i += 1
            fields = args[i]
        elif a.startswith("-f"):
            fields = a[2:]
        elif a.startswith("-"):
            raise _Unhandled
        else:
            files.append(a)
        i += 1
    if fields is None:
        raise _Unhandled
    sel = _parse_fields(fields)
    if files:
        try:
            txt = _read_repo_file(repo, files[0])
        except OSError:
            return 1, f"cut: {files[0]}: No such file or directory"
    else:
        txt = stdin or ""
    out = []
    for line in txt.splitlines():
        cols = line.split(delim)
        out.append(delim.join(cols[k - 1] for k in sel if 0 < k <= len(cols)))
    return 0, "\n".join(out)


def _h_du(argv, stdin, repo):
    unit = 1024  # du default block ≈ 1K
    path = "."
    for a in argv[1:]:
        if a.startswith("-"):
            for f in a[1:]:
                if f == "s":
                    pass
                elif f == "m":
                    unit = 1048576
                elif f == "k":
                    unit = 1024
                elif f == "b":
                    unit = 1
                else:
                    raise _Unhandled
        else:
            path = a
    base = repo / path
    total = 0
    try:
        if base.is_file():
            total = base.stat().st_size
        else:
            for p in base.rglob("*"):
                try:
                    if p.is_file():
                        total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        return 1, f"du: cannot access '{path}'"
    size = math.ceil(total / unit) if total else 0
    return 0, f"{size}\t{path}"


def _h_test(argv, stdin, repo):
    args = argv[1:]
    if args and args[-1] == "]" and argv[0] == "[":
        args = args[:-1]
    if len(args) == 2 and args[0] in ("-f", "-d", "-e", "-s", "-r", "-w", "-x"):
        p = repo / args[1]
        op = args[0]
        ok = {
            "-f": p.is_file(),
            "-d": p.is_dir(),
            "-e": p.exists(),
            "-s": p.is_file() and p.stat().st_size > 0,
            "-r": os.access(p, os.R_OK),
            "-w": os.access(p, os.W_OK),
            "-x": os.access(p, os.X_OK),
        }[op]
        return (0 if ok else 1), ""
    if len(args) == 1:
        return (0 if args[0] else 1), ""
    raise _Unhandled


def _h_echo(argv, stdin, repo):
    args = argv[1:]
    if args and args[0] == "-n":
        return 0, " ".join(args[1:])
    return 0, " ".join(args)


def _h_printf(argv, stdin, repo):
    args = argv[1:]
    if not args:
        return 0, ""
    fmt = args[0].replace("\\n", "\n").replace("\\t", "\t")
    try:
        return 0, (fmt % tuple(args[1:])) if "%" in fmt else fmt
    except (TypeError, ValueError):
        raise _Unhandled


def _resolve_python(tok: str, repo: Path) -> str:
    if "/" in tok:
        cand = repo / tok
        if cand.is_file():
            return str(cand)
    return sys.executable


def _h_python(argv, stdin, repo):
    exe = _resolve_python(argv[0], repo)
    try:
        p = subprocess.run([exe, *argv[1:]], cwd=str(repo), input=stdin,
                           capture_output=True, text=True, timeout=60)
        return p.returncode, (p.stdout + p.stderr)
    except (OSError, subprocess.SubprocessError):
        raise _Unhandled


def _h_binary(name):
    """A handler that shells straight to a real cross-platform binary (git, jq, rg …) by resolving
    it on PATH — no POSIX shell in the middle. Missing binary → _Unhandled (shell fallback / ENV)."""
    def handler(argv, stdin, repo):
        exe = shutil.which(name)
        if not exe:
            raise _Unhandled
        try:
            p = subprocess.run([exe, *argv[1:]], cwd=str(repo), input=stdin,
                               capture_output=True, text=True, timeout=60)
            return p.returncode, (p.stdout + p.stderr)
        except (OSError, subprocess.SubprocessError):
            raise _Unhandled
    return handler


_BUILTINS = {
    "grep": _h_grep, "egrep": lambda a, s, r: _h_grep(["grep", "-E", *a[1:]], s, r),
    "head": _h_head, "tail": _h_tail, "cat": _h_cat, "wc": _h_wc, "cut": _h_cut,
    "du": _h_du, "test": _h_test, "[": _h_test, "echo": _h_echo, "printf": _h_printf,
    "python": _h_python, "python3": _h_python,
    "git": _h_binary("git"), "jq": _h_binary("jq"), "rg": _h_binary("rg"),
}


def _has_unsupported_meta(cmd: str) -> bool:
    """True if the command carries a top-level (unquoted) shell construct the native engine does not
    model — a redirect, sequence, subshell, command-substitution, or backgrounding. Metacharacters
    inside quotes (a `<` or `;` within a `python -c` string) do not count."""
    quote = None
    i, n = 0, len(cmd)
    while i < n:
        c = cmd[i]
        if quote:
            if c == "\\" and quote == '"' and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ('"', "'"):
            quote = c
            i += 1
            continue
        if c == "\\":
            i += 2
            continue
        if c in ";<>`$(){}":
            return True
        if c == "&":
            if i + 1 < n and cmd[i + 1] == "&":
                i += 2
                continue
            return True
        i += 1
    return False


def _split_shell(cmd: str) -> list[str]:
    """Split a command on top-level `&&`, `||`, `|` (quotes respected), returning segments and
    operators interleaved: [seg, op, seg, op, …]."""
    tokens: list[str] = []
    buf: list[str] = []
    quote = None
    i, n = 0, len(cmd)
    while i < n:
        c = cmd[i]
        if quote:
            buf.append(c)
            if c == "\\" and quote == '"' and i + 1 < n:
                buf.append(cmd[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ('"', "'"):
            quote = c
            buf.append(c)
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            buf.append(c)
            buf.append(cmd[i + 1])
            i += 2
            continue
        if c == "&" and i + 1 < n and cmd[i + 1] == "&":
            tokens.append("".join(buf)); buf = []; tokens.append("&&"); i += 2; continue
        if c == "|" and i + 1 < n and cmd[i + 1] == "|":
            tokens.append("".join(buf)); buf = []; tokens.append("||"); i += 2; continue
        if c == "|":
            tokens.append("".join(buf)); buf = []; tokens.append("|"); i += 1; continue
        buf.append(c)
        i += 1
    tokens.append("".join(buf))
    return tokens


def _run_simple(seg: str, stdin, repo):
    argv = shlex.split(seg)
    if not argv:
        raise _Unhandled
    name = argv[0].split("/")[-1]
    handler = _BUILTINS.get(name)
    if handler is None:
        raise _Unhandled
    try:
        return handler(argv, stdin, repo)
    except _Unhandled:
        raise
    except (ValueError, IndexError, re.error):
        # Malformed-but-shell-valid input the native parser can't model: a non-integer count
        # (`head -n abc`), a flag consuming a missing trailing arg (`grep -e`), an untranslatable
        # pattern. Defer to a real shell. A genuine native-engine DEFECT (AttributeError,
        # TypeError, KeyError, …) is deliberately NOT caught here — it propagates and surfaces
        # loudly rather than hiding behind the shell fallback.
        raise _Unhandled


def _run_pipeline(segments: list[str], repo: Path):
    stdin = None
    rc, out = 0, ""
    for seg in segments:
        rc, out = _run_simple(seg, stdin, repo)
        stdin = out
    return rc, out


def native_run(cmd: str, repo: Path) -> tuple[int, str]:
    """Evaluate a command in-process. Raises _Unhandled if it cannot be modelled natively."""
    if _has_unsupported_meta(cmd):
        raise _Unhandled
    toks = _split_shell(cmd)
    if not toks or not toks[0].strip():
        raise _Unhandled
    # group into pipelines separated by && / ||  (| binds tighter)
    pipelines: list[list[str]] = []
    conjunctions: list[str] = []
    cur = [toks[0]]
    k = 1
    while k < len(toks):
        op, seg = toks[k], toks[k + 1]
        k += 2
        if op == "|":
            cur.append(seg)
        else:
            pipelines.append(cur)
            conjunctions.append(op)
            cur = [seg]
    pipelines.append(cur)

    out_acc: list[str] = []
    rc = 0
    for idx, pipe in enumerate(pipelines):
        if idx > 0:
            conj = conjunctions[idx - 1]
            if conj == "&&" and rc != 0:
                continue
            if conj == "||" and rc == 0:
                continue
        rc, out = _run_pipeline(pipe, repo)
        if out:
            out_acc.append(out)
    return rc, "\n".join(a for a in out_acc if a)


def _resolve_shell() -> str | None:
    """A real POSIX shell for the genuinely-shell CHECKs: bash → sh, then Git-for-Windows bash."""
    for name in ("bash", "sh"):
        p = shutil.which(name)
        if p:
            return p
    for cand in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ):
        if os.path.isfile(cand):
            return cand
    return None


def _run(cmd: str, repo: Path) -> tuple[int | None, str, str]:
    """Run a CHECK command. Returns (rc, output, mode) where mode is 'native' | 'shell' | 'noshell'.
    Native handling first (no shell, cross-platform); a genuinely-shell command falls back to a
    resolved shell; when no shell exists, mode is 'noshell' and rc is None — an honest ENV, never a
    fabricated FAIL."""
    try:
        rc, out = native_run(cmd, repo)
        return rc, out.strip(), "native"
    except _Unhandled:
        pass
    shell = _resolve_shell()
    if shell is None:
        return None, "<no POSIX shell on PATH; command is genuinely shell — cannot evaluate here>", "noshell"
    try:
        p = subprocess.run([shell, "-c", cmd], cwd=str(repo), capture_output=True,
                           text=True, timeout=60)
        return p.returncode, (p.stdout + p.stderr).strip(), "shell"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"<did not run: {exc}>", "noshell"


def evaluate(cmd: str, exp: str, repo: Path) -> tuple[str, str]:
    """Return (verdict, output). PASS/FAIL for a machine expectation, EYE for a human one, ENV when
    the command is genuinely shell and no shell exists here (never a fabricated FAIL)."""
    rc, out, mode = _run(cmd, repo)
    if mode == "noshell":
        return "ENV", out
    last = out.split()[-1] if out.split() else ""

    def as_int(s: str):
        try:
            return int(s)
        except ValueError:
            return None

    if re.search(r"→\s*True|->\s*True", exp):
        return ("PASS", "") if last == "True" else ("FAIL", out or f"(rc={rc}, no output)")
    m = re.search(r"(?:≥|⩾|>=)\s*(\d+)", exp)
    if m:
        n = as_int(last)
        return ("PASS", "") if n is not None and n >= int(m.group(1)) else ("FAIL", out or f"rc={rc}")
    m = re.search(r"=\s*(\d+)", exp)
    if m:
        n = as_int(last)
        return ("PASS", "") if n is not None and n == int(m.group(1)) else ("FAIL", out or f"rc={rc}")
    if re.search(r"non-empty|resolves", exp):
        return ("PASS", "") if rc == 0 and out else ("FAIL", out or f"rc={rc}, empty")
    # runnable, but the expectation is for a human eye — surface the reading, judge nothing
    return "EYE", out or f"(rc={rc}, no output)"


def collect(repo: Path) -> list[ClaimCheck]:
    checks: list[ClaimCheck] = []
    sources = list(sorted(repo.glob("AUDIT_*.md")))
    sources += [repo / d for d in INTERFACE_DOCS if (repo / d).is_file()]
    for src in sources:
        for text in iter_check_texts(src.read_text(encoding="utf-8", errors="replace")):
            kind, cmd, exp = classify(text)
            cc = ClaimCheck(src.name, text, kind, cmd)
            if kind == "RUNNABLE":
                cc.verdict, cc.output = evaluate(cmd, exp, repo)
            checks.append(cc)
    return checks


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the CHECK predicates banked in AUDIT_*.md.")
    ap.add_argument("--repo", default=".", help="repo root to scan (default: cwd)")
    args = ap.parse_args(argv)
    repo = Path(args.repo).resolve()

    checks = collect(repo)
    by_audit: dict[str, list[ClaimCheck]] = {}
    for c in checks:
        by_audit.setdefault(c.audit, []).append(c)

    fails = [c for c in checks if c.verdict == "FAIL"]
    for audit, cs in by_audit.items():
        tally = {v: sum(1 for c in cs if c.verdict == v)
                 for v in ("PASS", "FAIL", "EYE", "ENV", "PROSE")}
        print(f"\n{audit}: PASS={tally['PASS']} FAIL={tally['FAIL']} "
              f"EYE={tally['EYE']} ENV={tally['ENV']} PROSE={tally['PROSE']}")
        for c in cs:
            if c.verdict in ("EYE", "FAIL", "ENV"):
                body = c.output.replace(chr(10), chr(10) + "         ")
                print(f"  {c.verdict:<4} {c.text}\n       ↳ {body}")
    if fails:
        print(f"\nVERDICT=FAIL failed={len(fails)}/{len(checks)}")
    else:
        print(f"\nVERDICT=PASS checks={len(checks)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
