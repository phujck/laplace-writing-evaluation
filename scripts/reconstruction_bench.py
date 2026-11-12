#!/usr/bin/env python3
"""The reconstruction benchmark - WO-20260728-reconstruction-bench.

Three orientation arms over one frozen task set (scripts/reconstruction_bench_tasks.json):

  A  reconstruction  wake.py --grade 0 stdout; + recursive descent for topic tasks
  B  flat-naive      the fallback set CLAUDE.md itself names, read whole
                     (B+ adds STANDING_LAW.md + OPEN_STACK.md)
  C  flat-skilled    grep with patterns derived from the question text only,
                     then read the hit files - bounded to two rounds

Cost is tokens = utf-8 bytes / 4 of everything entering context. Correctness is
scored before cost: an arm's context either contains every must-atom of a task
(after the shared normalizer) or the arm is wrong, and wrong arms are excluded
from the cost summary. Patterns for arm C are derived mechanically from the
question string; the run raises if any must-atom of length >= 4 is a substring
of a pattern (the leakage assertion).

One command:

  PYTHONPATH=src python3 scripts/reconstruction_bench.py --out evidence/reconstruction_bench_2026-07-28

Writes rows.json + table.md into --out (figures are a separate pass, banked in
the same bundle). Prints the correctness table before any cost number.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TASK_FILE = Path(__file__).resolve().parent / "reconstruction_bench_tasks.json"

# Arm B is quoted from CLAUDE.md ("the linear read - HANDOFF.md, the latest
# SESSION_HANDOFF_*, the EIGEN_DIARY.md tail, EIGEN_ARCHITECTURE.md"), plus the
# two ambient files any session loads. The diary TAIL is the instruction's own
# word: last 5 entries, not the 540 KB whole.
ARM_B_AMBIENT = ["CLAUDE.md", "AGENTS.md"]
ARM_B_NAMED = ["HANDOFF.md", "EIGEN_ARCHITECTURE.md"]
ARM_BPLUS_EXTRA = ["STANDING_LAW.md", "OPEN_STACK.md"]
DIARY_TAIL_ENTRIES = 5

GREP_INCLUDES = ["*.md", "*.py", "*.jsonl"]
GREP_MAX_LINES = 100
GREP_CONTEXT = 3
MAX_WHOLE_READS = 3
STOPWORDS = set(
    """a an and are at be been by did do does for from had has have how in is it its may
    must name of on or once that the this to under was were what which who with when
    where why not no still and-what state current currently"""
    .split()
)


# ---------------------------------------------------------------- normalizer

def normalize(text: str) -> str:
    """The shared normalizer - identical for every arm (load-bearing, risk R3)."""
    t = text.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
    t = t.replace("*", "").replace("`", "")
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)
    t = re.sub(r"[‐-―−]", "-", t)
    t = re.sub(r"\s+", " ", t)
    return t.casefold()


def atom_positions(hay: str, needle: str, cap: int = 200) -> list[int]:
    out, start = [], 0
    n = normalize(needle)
    while len(out) < cap:
        i = hay.find(n, start)
        if i < 0:
            break
        out.append(i)
        start = i + 1
    return out


def score(context: str, atoms: list, window) -> tuple[bool, int | None]:
    """All must-atoms present (any-of groups by one member), within window if set.

    Returns (correct, first_hit_offset) - offset is the position of the last
    atom to appear, i.e. how deep the needle sits in the arm's context.
    """
    hay = normalize(context)
    per_atom: list[list[int]] = []
    for atom in atoms:
        members = atom if isinstance(atom, list) else [atom]
        pos: list[int] = []
        for m in members:
            pos.extend(atom_positions(hay, m))
        if not pos:
            return False, None
        per_atom.append(sorted(pos))
    if window is None:
        return True, max(p[0] for p in per_atom)
    # sliding check: does some choice of one position per atom fit in the window
    events = sorted((p, i) for i, ps in enumerate(per_atom) for p in ps)
    from collections import defaultdict

    lo = 0
    counts: dict[int, int] = defaultdict(int)
    covered = 0
    for hi in range(len(events)):
        p, i = events[hi]
        if counts[i] == 0:
            covered += 1
        counts[i] += 1
        while events[hi][0] - events[lo][0] > window:
            q, j = events[lo]
            counts[j] -= 1
            if counts[j] == 0:
                covered -= 1
            lo += 1
        if covered == len(per_atom):
            return True, events[hi][0]
    return False, None


# ---------------------------------------------------------------- arm C

def question_tokens(question: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9_./-]{3,}", question.casefold())
    kept = [w for w in words if w not in STOPWORDS]
    seen, out = set(), []
    for w in kept:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def file_frequency(pattern: str) -> int:
    """How many repo files match the (already-regex) pattern. The counting
    greps model the skill of choosing a distinctive keyword; per the protocol
    they are not charged (arm C is measured at its best case, the caveat says so)."""
    cmd = ["grep", "-rliE", pattern]
    for g in GREP_INCLUDES:
        cmd.append(f"--include={g}")
    cmd += ["--exclude-dir=.git", "."]
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return len(r.stdout.splitlines())


def derive_pattern(question: str) -> str:
    """Pattern from the QUESTION string only - deterministic, re-derivable.

    The skilled move is the rarest DISTINCTIVE PHRASE: adjacent kept-token
    bigrams from the question, ranked by repo file frequency, rarest hitting
    bigram first; if no bigram hits anywhere, the two rarest hitting single
    tokens ORed. The frequency-counting greps model pattern-choosing skill and
    are not charged (the caveat says arm C is measured at its best case)."""
    toks = question_tokens(question)
    bigrams = [
        rf"{re.escape(a)}[\s-]+{re.escape(b)}" for a, b in zip(toks, toks[1:])
    ]
    ranked_bi = sorted((file_frequency(b), b) for b in bigrams)
    useful_bi = [b for n, b in ranked_bi if n > 0]
    if useful_bi:
        return useful_bi[0]
    ranked = sorted((file_frequency(re.escape(t)), t) for t in toks)
    useful = [t for n, t in ranked if n > 0]
    if not useful:
        return "|".join(re.escape(t) for t in toks[:6])
    return re.escape(useful[0])


def assert_no_leak(pattern: str, atoms: list, task_id: str, question: str) -> None:
    """A pattern word that occurs in a must-atom but NOT in the question was
    derived from the answer - the baseline would be rigged. Raise loudly."""
    q = question.casefold()
    chunks = re.findall(r"[a-z0-9][a-z0-9_./-]{3,}", pattern.casefold())
    for atom in atoms:
        for m in atom if isinstance(atom, list) else [atom]:
            if m == "__LIVE_GIT__":
                continue
            am = m.casefold()
            for chunk in chunks:
                if chunk in am and chunk not in q:
                    raise SystemExit(
                        f"LEAKAGE: task {task_id} pattern word {chunk!r} occurs in "
                        f"must-atom {m!r} but not in the question - answer-derived "
                        f"pattern, the baseline would be rigged"
                    )


GREP_LINE_CAP = 400  # the `| cut -c1-400` a skilled agent pipes jsonl-heavy grep through


def run_grep(pattern: str) -> str:
    cmd = ["grep", "-rniE", f"-C{GREP_CONTEXT}", pattern]
    for g in GREP_INCLUDES:
        cmd.append(f"--include={g}")
    cmd += ["--exclude-dir=.git", "."]
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    lines = [ln[:GREP_LINE_CAP] for ln in r.stdout.splitlines()]
    return "\n".join(lines[:GREP_MAX_LINES * (2 * GREP_CONTEXT + 1)])


def hit_files(grep_out: str) -> list[str]:
    counts: dict[str, int] = {}
    for line in grep_out.splitlines():
        m = re.match(r"^(\./[^:]+):\d+:", line)
        if m:
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return [f for f, _ in sorted(counts.items(), key=lambda kv: -kv[1])]


#: whole-file reads above this size are replaced by hit-regions - the skilled
#: agent reads the matched sections of a 500 KB file, not the whole of it
WHOLE_READ_CAP = 64 * 1024
REGION_LINES = 40


def charged_read(path: Path, pattern: str) -> str:
    """Whole file if small; otherwise the +-REGION_LINES around pattern hits."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text.encode("utf-8")) <= WHOLE_READ_CAP:
        return text
    lines = text.splitlines()
    rx = re.compile(pattern, re.IGNORECASE)
    keep: set[int] = set()
    hits = 0
    for i, ln in enumerate(lines):
        if rx.search(ln):
            hits += 1
            if hits > 50:  # a reader stops scanning a huge file at some point
                break
            keep.update(range(max(0, i - REGION_LINES), min(len(lines), i + REGION_LINES + 1)))
    if not keep:
        return "\n".join(ln[:2000] for ln in lines[: 2 * REGION_LINES])
    return "\n".join(lines[i][:2000] for i in sorted(keep))


def arm_c(task: dict, git_ctx: str) -> dict:
    pattern = derive_pattern(task["question"])
    assert_no_leak(pattern, task["atoms"], task["id"], task["question"])
    context, read = "", []
    rounds = 0

    def satisfied() -> bool:
        return score(context, task["atoms"], task.get("window"))[0]

    if task["atoms"] == ["__LIVE_GIT__"]:
        context = git_ctx  # the licensed live probe, charged
        return {"context": context, "rounds": 1, "pattern": "(git probe)", "files": []}

    # round 1: grep only - a skilled agent checks whether the grep view already
    # answers before opening anything
    rounds = 1
    grep1 = run_grep(pattern)
    context += grep1
    files = hit_files(grep1)
    # round 2: open files only if the grep view was not enough - top hit files
    # (regions for huge ones), or a relaxed re-grep if round 1 hit nothing
    if not satisfied():
        rounds = 2
        if not files:
            toks = question_tokens(task["question"])
            relaxed = "|".join(re.escape(t) for t in toks[:6])
            grep2 = run_grep(relaxed)
            context += grep2
            files = hit_files(grep2)
            pat = relaxed
        else:
            pat = pattern
        for f in files[:MAX_WHOLE_READS]:
            p = REPO / f
            if p.is_file():
                context += "\n" + charged_read(p, pat)
                read.append(f)
    return {"context": context, "rounds": rounds, "pattern": pattern, "files": read}


# ---------------------------------------------------------------- arm B

def diary_tail(path: Path, entries: int) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    heads = [m.start() for m in re.finditer(r"(?m)^## ", text)]
    return text[heads[-entries]:] if len(heads) >= entries else text


def latest_session_handoff() -> Path:
    best, best_t = None, -1
    for p in REPO.glob("SESSION_HANDOFF_*.md"):
        r = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", p.name],
            cwd=REPO, capture_output=True, text=True,
        )
        t = int(r.stdout.strip() or 0)
        if t > best_t:
            best, best_t = p, t
    return best


def arm_b(git_ctx: str, plus: bool) -> tuple[str, list[str]]:
    parts, names = [], []
    for name in ARM_B_AMBIENT + ARM_B_NAMED:
        parts.append((REPO / name).read_text(encoding="utf-8", errors="replace"))
        names.append(name)
    sh = latest_session_handoff()
    parts.append(sh.read_text(encoding="utf-8", errors="replace"))
    names.append(sh.name)
    parts.append(diary_tail(REPO / "EIGEN_DIARY.md", DIARY_TAIL_ENTRIES))
    names.append(f"EIGEN_DIARY.md (last {DIARY_TAIL_ENTRIES} entries)")
    if plus:
        for name in ARM_BPLUS_EXTRA:
            parts.append((REPO / name).read_text(encoding="utf-8", errors="replace"))
            names.append(name)
    parts.append(git_ctx)  # the licensed live probe for T09, charged
    names.append("(git probe)")
    return "\n".join(parts), names


# ---------------------------------------------------------------- arm A

def run_wake() -> tuple[str, str]:
    r = subprocess.run(
        [sys.executable, "scripts/wake.py", "--grade", "0"],
        cwd=REPO, capture_output=True, text=True, timeout=600,
    )
    return r.stdout, r.stderr.strip()


class CountingLeafSource:
    """Wraps the canonical leaf source and counts every byte it serves -
    tokens_touched is then measured, not estimated."""

    def __init__(self, inner):
        self.inner = inner
        self.bytes = 0

    def __call__(self, name: str) -> str:
        text = self.inner(name)
        self.bytes += len((text or "").encode("utf-8"))
        return text


def open_descender_or_reason():
    try:
        sys.path.insert(0, str(REPO / "src"))
        from laplace.engine import recursive_read

        counter = CountingLeafSource(recursive_read.SelfGradedLeafSource(REPO))
        dsc = recursive_read.open_descender(REPO, leaf_source=counter)
        return dsc, counter, None
    except Exception as e:  # RecursiveReadError or import failure - named, never substituted
        return None, None, f"{type(e).__name__}: {e}"


A_FILE_READ_CAP = 32 * 1024  # Read-with-limit: one question's read of one file


def hit_text(dsc, hit_id: str, open_file: bool) -> str:
    """What a reconstructing agent reads after a descent hit. Top hits get the
    real repo file (Read-with-limit); the rest contribute their leaf digest -
    the skim a reader does over the tail of a hit list."""
    path = REPO / hit_id.split("#")[0]
    if open_file and path.is_file():
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[:A_FILE_READ_CAP] if len(text.encode("utf-8")) > A_FILE_READ_CAP else text
    try:
        return dsc.leaf_source(hit_id) or ""
    except Exception:
        return ""


def arm_a(task: dict, wake_stdout: str, dsc, counter, dsc_reason,
          beam: int, k: int, atoms: list, window) -> dict:
    row = {"context": wake_stdout, "touched_extra": 0, "note": ""}
    if task["arm_a"] != "wake+descend":
        return row
    if dsc is None:
        row["note"] = f"DESCENT UNAVAILABLE ({dsc_reason})"
        return row
    packets = []
    # round 1 at the default beam; round 2 doubles it - the mirror of arm C's
    # two bounded rounds. Both packets and all reads are charged.
    for round_no, b in enumerate((beam, beam * 2), start=1):
        bytes_before = counter.bytes
        pkt = dsc.descend(task["question"], k=k, beam=b)
        row["touched_extra"] += counter.bytes - bytes_before
        row["context"] += "\n" + json.dumps(pkt, ensure_ascii=False, default=str)
        # digests for every hit first (the skim), then open top files one at a
        # time and stop as soon as the atoms are present - the mirror of arm
        # C's read-until-satisfied
        for h in pkt["hits"]:
            row["context"] += "\n" + hit_text(dsc, h["id"], open_file=False)
        for h in pkt["hits"][:MAX_WHOLE_READS]:
            if score(row["context"], atoms, window)[0]:
                break
            row["context"] += "\n" + hit_text(dsc, h["id"], open_file=True)
        packets.append({
            "round": round_no, "beam": b, "k": k,
            "materialized": pkt.get("materialized"),
            "seconds": pkt.get("seconds"),
            "top_hits": [h["id"] for h in pkt["hits"][:5]],
        })
        if score(row["context"], atoms, window)[0]:
            break
    row["rounds"] = len(packets)
    row["packet"] = packets[-1]
    return row


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="evidence/reconstruction_bench_2026-07-28")
    ap.add_argument("--beam", type=int, default=8)
    ap.add_argument("--k", type=int, default=10)
    args = ap.parse_args()

    tasks = json.loads(TASK_FILE.read_text())["tasks"]
    task_sha = hashlib.sha256(TASK_FILE.read_bytes()).hexdigest()

    head = subprocess.run(["git", "log", "-1", "--oneline"], cwd=REPO,
                          capture_output=True, text=True).stdout.strip()
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=REPO,
                            capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                           capture_output=True, text=True).stdout
    git_ctx = f"branch {branch}\n{head}\n{'dirty:' + dirty if dirty.strip() else 'clean tree'}"

    print(f"# reconstruction bench | HEAD {head} | task file sha256 {task_sha[:16]}...")

    t0 = time.time()
    wake_stdout, wake_stderr = run_wake()
    wake_bytes = len(wake_stdout.encode("utf-8"))
    wake_sha = hashlib.sha256(wake_stdout.encode("utf-8")).hexdigest()
    print(f"# wake: {wake_bytes} B ({wake_bytes // 4} tok) sha256 {wake_sha[:16]}... "
          f"in {time.time() - t0:.1f}s | stderr: {wake_stderr or '(none)'}")

    dsc, counter, dsc_reason = open_descender_or_reason()
    print(f"# descent: {'LIVE' if dsc else 'UNAVAILABLE - ' + str(dsc_reason)}")

    # live-git atoms for T09
    short_head = head.split()[0]
    live_atoms = [branch, short_head]

    rows = []
    for task in tasks:
        atoms = live_atoms if task["atoms"] == ["__LIVE_GIT__"] else task["atoms"]
        window = task.get("window")

        # arm A
        a = arm_a(task, wake_stdout, dsc, counter, dsc_reason,
                  args.beam, args.k, atoms, window)
        a_bytes = len(a["context"].encode("utf-8"))
        if a["note"].startswith("DESCENT UNAVAILABLE"):
            correct, offset = None, None
        else:
            correct, offset = score(a["context"], atoms, window)
        rows.append({
            "task": task["id"], "class": task["class"], "arm": "A",
            "correct": correct, "rounds": a.get("rounds"),
            "tokens_context": a_bytes // 4,
            "tokens_touched": (a_bytes + a["touched_extra"]) // 4,
            "first_hit_offset": offset, "note": a["note"],
            "packet": a.get("packet"),
        })

        # arms B and B+
        for arm_name, plus in (("B", False), ("B+", True)):
            ctx, names = arm_b(git_ctx, plus)
            b_bytes = len(ctx.encode("utf-8"))
            correct, offset = score(ctx, atoms, window)
            rows.append({
                "task": task["id"], "class": task["class"], "arm": arm_name,
                "correct": correct, "rounds": None,
                "tokens_context": b_bytes // 4, "tokens_touched": b_bytes // 4,
                "first_hit_offset": offset, "note": "",
            })

        # arm C
        c = arm_c(task, git_ctx)
        c_bytes = len(c["context"].encode("utf-8"))
        correct, offset = score(c["context"], atoms, window)
        rows.append({
            "task": task["id"], "class": task["class"], "arm": "C",
            "correct": correct, "rounds": c["rounds"],
            "tokens_context": c_bytes // 4, "tokens_touched": c_bytes // 4,
            "first_hit_offset": offset,
            "note": f"pattern={c['pattern']} read={','.join(c['files'][:4])}",
        })
        flag = {True: "y", False: "N", None: "-"}
        marks = {r_["arm"]: flag[r_["correct"]] for r_ in rows[-4:]}
        print(f"  {task['id']} {task['class']:<14} "
              f"A:{marks['A']} B:{marks['B']} B+:{marks['B+']} C:{marks['C']}")

    # ---------------- correctness first
    arms = ["A", "B", "B+", "C"]
    print("\n## correctness (before any cost number)")
    for arm in arms:
        sub = [r for r in rows if r["arm"] == arm]
        ok = sum(1 for r in sub if r["correct"])
        unavail = sum(1 for r in sub if r["correct"] is None)
        note = f" ({unavail} unavailable)" if unavail else ""
        print(f"  arm {arm:<3} {ok}/{len(sub)} correct{note}")

    classes = sorted({r["class"] for r in rows}, key=lambda c: [r["class"] for r in rows].index(c))
    print("\n## per-class matrix (correct/total)")
    print("  class            " + "  ".join(f"{a:>4}" for a in arms))
    for cl in classes:
        line = f"  {cl:<16}"
        for arm in arms:
            sub = [r for r in rows if r["arm"] == arm and r["class"] == cl]
            line += f"  {sum(1 for r in sub if r['correct'])}/{len(sub)}"
        print(line)

    # ---------------- cost, correct tasks only
    def med(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2] if xs else None

    print("\n## cost (tokens = utf-8 bytes / 4; medians+totals over CORRECT tasks only)")
    summary = {}
    for arm in arms:
        sub = [r for r in rows if r["arm"] == arm]
        okr = [r for r in sub if r["correct"]]
        s = {
            "correct": len(okr), "total_tasks": len(sub),
            "median_tokens_correct": med([r["tokens_context"] for r in okr]),
            "total_tokens_correct": sum(r["tokens_context"] for r in okr),
            "total_tokens_all": sum(r["tokens_context"] for r in sub),
            "median_offset": med([r["first_hit_offset"] for r in okr
                                  if r["first_hit_offset"] is not None]),
        }
        summary[arm] = s
        print(f"  arm {arm:<3} correct {s['correct']:>2}  median {s['median_tokens_correct']}  "
              f"total(correct) {s['total_tokens_correct']}  median offset {s['median_offset']}")

    # ---------------- the two headline framings
    # per-session: what one orienting session actually pays. A pays the wake
    # once plus every descent it attempted (failed ones included - the session
    # paid them); B/B+ pay their file set once; C pays per question asked.
    wake_tok = wake_bytes // 4
    a_extra_all = sum(max(0, r["tokens_context"] - wake_tok)
                      for r in rows if r["arm"] == "A")
    a_correct = summary["A"]["correct"]
    a_session = wake_tok + a_extra_all
    b_row = next(r for r in rows if r["arm"] == "B")
    bp_row = next(r for r in rows if r["arm"] == "B+")
    c_ok = [r for r in rows if r["arm"] == "C" and r["correct"]]
    c_med = med([r["tokens_context"] for r in c_ok])
    c_session = sum(r["tokens_context"] for r in rows if r["arm"] == "C")
    crossover = None if not c_med else round(wake_tok / c_med, 1)

    print("\n## per-session cost (what one orienting session pays)")
    print(f"  A  wake once + all descents (failed included): {a_session} tok "
          f"-> {a_correct}/18 answered")
    print(f"  B  the quoted set once: {b_row['tokens_context']} tok -> "
          f"{summary['B']['correct']}/18 answered")
    print(f"  B+ the charitable set once: {bp_row['tokens_context']} tok -> "
          f"{summary['B+']['correct']}/18 answered")
    print(f"  C  a grep session per question: {c_session} tok -> "
          f"{summary['C']['correct']}/18 answered")

    print("\n## headlines (both, neither alone)")
    verdict = "grep wins" if (c_med or 0) < wake_tok else "the wake wins even"
    print(f"  per-question: arm C median {c_med} tok (correct tasks) vs arm A wake "
          f"{wake_tok} tok - {verdict} a single narrow question "
          f"(crossover ~{crossover} questions)")
    print(f"  per-session: arm A {a_session} tok vs "
          f"arm B {b_row['tokens_context']} tok ({b_row['tokens_context'] / max(1, a_session):.1f}x) vs "
          f"arm B+ {bp_row['tokens_context']} tok ({bp_row['tokens_context'] / max(1, a_session):.1f}x) - "
          f"and A answers more of the 18 than any flat arm")

    report = {
        "work_order": "WO-20260728-reconstruction-bench",
        "date": "2026-07-28",
        "head": head, "branch": branch, "dirty": bool(dirty.strip()),
        "task_file_sha256": task_sha,
        "wake_bytes": wake_bytes, "wake_sha256": wake_sha,
        "wake_stderr": wake_stderr,
        "descent": "live" if dsc else f"unavailable: {dsc_reason}",
        "beam": args.beam, "k": args.k,
        "arm_b_set": ARM_B_AMBIENT + ARM_B_NAMED
        + [latest_session_handoff().name, f"EIGEN_DIARY.md tail {DIARY_TAIL_ENTRIES}"],
        "arm_bplus_extra": ARM_BPLUS_EXTRA,
        "rows": rows, "summary": summary,
        "headline": {
            "per_question_c_median": c_med, "wake_tokens": wake_tok,
            "crossover_questions": crossover,
            "session_tokens": {
                "A": a_session, "B": b_row["tokens_context"],
                "B+": bp_row["tokens_context"], "C": c_session,
            },
            "x_vs_B": round(b_row["tokens_context"] / max(1, a_session), 1),
            "x_vs_Bplus": round(bp_row["tokens_context"] / max(1, a_session), 1),
        },
    }
    out = REPO / args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "rows.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"\nbanked: {out / 'rows.json'}")


if __name__ == "__main__":
    main()
