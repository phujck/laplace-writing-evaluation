"""WO-20260821-arm-paths-die-on-a-space — the arm-quoting wiring gate.

THE DISEASE. The workflow arms build shell commands as text. ``q()`` emits a
DOUBLE-quoted shell word, which is correct in plain argv position — but written
INSIDE a ``python -c "..."`` payload its double quotes CLOSE the shell's own
double-quoted argument. A path containing a SPACE then splits into separate argv
words and the command dies (NameError / SyntaxError) before any reader runs.
``synthetics papers/<project>/manuscript`` is exactly such a path, so those arms
had never been runnable verbatim on that corpus.

THE CURE, and what this file guards:

  * ``pq(s)`` — a PYTHON string literal for a python-literal position inside a
    double-quoted ``-c`` payload. TWO unescapings happen in order (the shell
    strips its double-quote escapes, then Python parses the literal), so pq()
    encodes for both.
  * ``sq(s)`` — ONE POSIX single-quoted shell word, for argv positions that
    share a line with a ``-c`` payload.
  * ``q(s)`` — retained, and legal ONLY where the double quotes are outermost.

The static gates below are the row's own accept (zero ``${q(`` on any line that
opens a ``-c "`` payload) plus the soundness condition that gate depends on. The
live gate drives a REAL shell through the helpers lifted verbatim out of the arm
source, with a path that contains a space, and asserts the old form still dies —
a green suite that never ran a spaced path would be the same blindness again.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ARMS = [
    ".claude/workflows/project-harnessed.js",
    ".claude/workflows/project-fixedpoint.js",
]
PAYLOAD_OPEN = '-c "'

# A path shaped like the one the row names, plus the characters that would break
# a naive single-quoter: an apostrophe, a dollar, a backtick, a double quote and
# a backslash all have to survive BOTH unescaping layers.
SPACED = "synthetics papers/dp-a1/manuscript/main.tex"
HOSTILE = "synthetics papers/it's a \"weird\" $HOME `dir` with\\slash/main.tex"

NODE = shutil.which("node")

# Lift q/sq/pq out of the arm source itself and print what they emit for a value.
# Slicing the SOURCE (never a re-typed copy) is what makes this a wiring test:
# it fails if the shipped helpers regress, not if a transcription drifts.
_LIFT_JS = r"""
const { readFileSync } = require('node:fs')
const src = readFileSync(process.argv[1], 'utf8')
const i = src.indexOf('const q = (s) =>')
const p = src.indexOf('const pq = (s) =>')
if (i < 0 || p < 0) throw new Error('quoting helpers not found in ' + process.argv[1])
const j = src.indexOf('\n}', p) + 2
const { q, sq, pq } = (0, eval)(src.slice(i, j) + '\n;({ q, sq, pq })')
const v = process.argv[2]
process.stdout.write(JSON.stringify({ q: q(v), sq: sq(v), pq: pq(v) }))
"""


def _lines(rel: str) -> list[str]:
    return (REPO / rel).read_text(encoding="utf-8").split("\n")


def _quoted(rel: str, value: str) -> dict[str, str]:
    out = subprocess.run(
        [NODE, "-e", _LIFT_JS, "--", str(REPO / rel), value],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, f"lifting the helpers failed: {out.stderr[:400]}"
    return json.loads(out.stdout)


def _bash(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", cmd], capture_output=True, text=True, cwd=REPO, timeout=60,
    )


# ---- the static gates ------------------------------------------------------

@pytest.mark.parametrize("rel", ARMS)
def test_no_double_quoter_inside_a_c_payload(rel: str) -> None:
    """The row's own accept: ``${q(`` may not appear on a ``-c "`` line."""
    bad = [
        (n + 1, line.strip()[:140])
        for n, line in enumerate(_lines(rel))
        if PAYLOAD_OPEN in line and "${q(" in line
    ]
    assert not bad, (
        f"{rel}: q() emits DOUBLE quotes, which close the shell's own -c payload — "
        f"a path with a space dies there. Use pq() in a python-literal position and "
        f"sq() in an argv position. Offending lines: {bad}"
    )


@pytest.mark.parametrize("rel", ARMS)
def test_every_c_payload_closes_on_its_own_line(rel: str) -> None:
    """Soundness of the line-based gate above: a payload that spanned lines would
    hide a ``${q(`` on a continuation line, and the gate would go blind."""
    for n, line in enumerate(_lines(rel)):
        start = 0
        while (i := line.find(PAYLOAD_OPEN, start)) >= 0:
            rest = line[i + len(PAYLOAD_OPEN):]
            assert '"' in rest, (
                f"{rel}:{n + 1} opens a -c payload that does not close on the same "
                f"line; the line-based quoting gate cannot see into it."
            )
            start = i + len(PAYLOAD_OPEN)


@pytest.mark.parametrize("rel", ARMS)
def test_both_layer_quoters_are_defined(rel: str) -> None:
    src = (REPO / rel).read_text(encoding="utf-8")
    assert "const pq = (s) =>" in src, f"{rel}: no pq() (the python-literal quoter)"
    assert "const sq = (s) =>" in src, f"{rel}: no sq() (the shell-word quoter)"


# ---- the live gate: a real shell, a real spaced path -----------------------

@pytest.mark.skipif(NODE is None, reason="node is needed to lift the JS helpers")
@pytest.mark.parametrize("rel", ARMS)
@pytest.mark.parametrize("value", [SPACED, HOSTILE], ids=["spaced", "hostile"])
def test_pq_round_trips_a_spaced_path_through_a_real_payload(rel: str, value: str) -> None:
    """pq() in python-literal position: the value reaches Python intact."""
    pq = _quoted(rel, value)["pq"]
    r = _bash(f'python3 -c "import sys; sys.stdout.write({pq})"')
    assert r.returncode == 0, f"{rel}: pq() payload died: {r.stderr[:400]}"
    assert r.stdout == value, f"{rel}: pq() mangled the value: {r.stdout!r}"


@pytest.mark.skipif(NODE is None, reason="node is needed to lift the JS helpers")
@pytest.mark.parametrize("rel", ARMS)
@pytest.mark.parametrize("value", [SPACED, HOSTILE], ids=["spaced", "hostile"])
def test_sq_round_trips_a_spaced_path_in_argv_position(rel: str, value: str) -> None:
    """sq() in argv position after a payload: the value arrives as ONE word."""
    sq = _quoted(rel, value)["sq"]
    r = _bash(f'python3 -c "import sys; sys.stdout.write(sys.argv[1])" {sq}')
    assert r.returncode == 0, f"{rel}: sq() argv died: {r.stderr[:400]}"
    assert r.stdout == value, f"{rel}: sq() mangled the value: {r.stdout!r}"


@pytest.mark.skipif(NODE is None, reason="node is needed to lift the JS helpers")
@pytest.mark.parametrize("rel", ARMS)
def test_the_disease_still_reproduces_under_the_old_quoter(rel: str) -> None:
    """The inverted check. q() inside a payload MUST still break on a spaced path —
    if this ever passes, q() has silently become a single-quoter and the static
    gates above are guarding a name rather than a defect."""
    dq = _quoted(rel, SPACED)["q"]
    r = _bash(f'python3 -c "import sys; sys.stdout.write({dq})"')
    assert r.returncode != 0, (
        f"{rel}: q() inside a -c payload no longer fails on a spaced path — the gates "
        f"in this file are now testing a rename, not the defect. Re-derive them."
    )


@pytest.mark.skipif(NODE is None, reason="node is needed to lift the JS helpers")
@pytest.mark.parametrize("rel", ARMS)
def test_repaired_arm_shape_two_paths_in_one_argv_list(rel: str) -> None:
    """The verdict_io ``assemble`` shape: two pq() paths inside one Python list
    inside one double-quoted payload — the form that carried the defect."""
    d = _quoted(rel, "synthetics papers/dp-a1/manuscript")["pq"]
    f = _quoted(rel, "synthetics papers/dp-a1/manuscript/lock.json")["pq"]
    r = _bash(f"""python3 -c "import json; print(json.dumps(['assemble',{d},{f}]))" """)
    assert r.returncode == 0, f"{rel}: assemble-shape payload died: {r.stderr[:400]}"
    assert json.loads(r.stdout) == [
        "assemble",
        "synthetics papers/dp-a1/manuscript",
        "synthetics papers/dp-a1/manuscript/lock.json",
    ]
