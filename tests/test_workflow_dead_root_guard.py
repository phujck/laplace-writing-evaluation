"""WO-20260820-workflow-dead-root-guard: the cheap guard.

The bootstrap idiom in .claude/workflows/*.js resolves REPO_ROOT from
`args.repoRoot` / `git rev-parse --show-toplevel`, never from a baked-in
absolute path. A hardcoded `/home/<user>/<repo>` literal is exactly the
restriction-era scar this close pass excises (WO-20260820-excise-the-
restriction-era-bloat) and the failure mode WO-20260820-sewup-help-hangs
adjacent work uncovered: a dead path silently no-ops instead of failing loud.

This test fails if any workflow file carries such a literal OUTSIDE a
comment. Comments are allowed to mention the old dead path (several files
already do, as a "this used to be hardcoded" note) — only live code matters.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".claude" / "workflows"

# A two-segment absolute home path: /home/<user>/<repo-like-segment>. This is
# the shape of a dead machine-specific root (e.g. /home/phujck/VScodeProjects/laplace),
# not a generic /home/ mention.
HOME_LITERAL_RE = re.compile(r"/home/[^/\s'\"` \\]+/[^/\s'\"` \\]+")


def _strip_js_comments(text: str) -> str:
    """Strip // line comments and /* */ block comments.

    Deliberately simple (no string-literal awareness for `//` inside strings —
    none of these workflow files put `//` inside a string literal); good enough
    for a guard whose job is to ignore comment-only mentions of the dead path.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def _workflow_files() -> list[Path]:
    assert WORKFLOWS_DIR.is_dir(), f"expected workflows dir at {WORKFLOWS_DIR}"
    files = sorted(WORKFLOWS_DIR.glob("*.js"))
    assert files, f"no workflow .js files found under {WORKFLOWS_DIR}"
    return files


def test_no_dead_home_root_literal_outside_comments():
    offenders = {}
    for f in _workflow_files():
        code_only = _strip_js_comments(f.read_text())
        hits = HOME_LITERAL_RE.findall(code_only)
        if hits:
            offenders[f.name] = hits
    assert not offenders, (
        "workflow file(s) carry a hardcoded /home/<user>/<repo> literal outside "
        f"comments — resolve REPO_ROOT from args.repoRoot / git rev-parse "
        f"--show-toplevel instead: {offenders}"
    )


def test_guard_actually_detects_a_dead_root_literal():
    """Sanity check: the regex + comment-strip actually catches the shape it exists for."""
    sample = (
        "// this used to hardcode /home/user/laplace, fixed below\n"
        "let REPO_ROOT = '/home/phujck/VScodeProjects/laplace'\n"
    )
    code_only = _strip_js_comments(sample)
    assert HOME_LITERAL_RE.findall(code_only) == ["/home/phujck/VScodeProjects"]
