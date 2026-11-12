#!/usr/bin/env python3
"""audit_register.py — the register conjugate: scan rule-bearing surfaces for tics.

The register law (STANDING_LAW.md, 2026-07-21): rule-bearing text states instructions
plainly, once. Ritual emphasis, virtue adjectives, self-praise, and repeated formulas
are defects. The register sweep cleaned the rule-bearing surfaces; this script is the
conjugate that keeps them clean — it re-scans those surfaces for a small tic lexicon
and counts the hits per file.

THE BASELINE IS DEAD (W-register, PRM-20260721-register-zero): the register law is now
ABSOLUTE ZERO, not at-or-below a banked stock. ``corpus_friction/register_baseline.json``
carries an empty ``files`` map — any tic on any scanned file is a breach. Exit 0 only at
a genuine corpus-wide zero; exit 1 on any tic. The close wires this in two ways: the
``register`` row (WARN-tier conjugate) and the ``register_zero`` row (FAIL-eligible once
armed — the absolute-zero gate).

Scanned surfaces:
  * STANDING_LAW.md, CLAUDE.md            — whole text
  * profiles/**/*.yaml                    — whole text (comments + string values)
  * src/laplace/**/*.py                   — docstrings only (via ast; code strings are
                                            not rule-bearing prose and are left alone)
  * src/laplace/web/static_shared/*.mjs/.html — whole text (rendered interface copy;
                                            top level only, no vendored subtrees)

The lexicon (small, by design). The first five apply to every scanned surface; the
last three guard the served interface copy (.mjs/.html) only (scope ``_SERVED``):
  * honest / honestly as a virtue adverb-adjective (the term-of-art "honest-empty" is
    excluded — it names a degradation mode, not a virtue)
  * "his word" as the recurring formula (not the plural "his words" of attribution)
  * "never the rule" as the recurring formula
  * a run of three-or-more consecutive ALL-CAPS words (an incantation run)
  * "the ONE" emphatic
  * [served] sec:sN — a raw LaTeX section anchor shown as a UI label
  * [served] a full source module path (src/laplace/….py|.mjs|.html) in served copy
  * [served] a raw record/ruling id (PV-/RW-/PRM-/RM-/PRF-<digits>) above the fold

Run:
    python3 scripts/audit_register.py                 # scan, compare to baseline
    python3 scripts/audit_register.py --update-baseline   # rewrite the baseline
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_REL = "corpus_friction/register_baseline.json"

# --- surface classes ---------------------------------------------------------
# A detector may apply to every scanned surface (``_ALL``) or only to the served
# interface copy (``_SERVED`` — the rendered .mjs/.html "above the fold"). Scoping
# keeps the served-only breach classes (module paths, raw ids, section anchors) from
# firing on the docstrings/law prose that legitimately cite them in passing.
_ALL: frozenset[str] | None = None
_SERVED: frozenset[str] = frozenset({"served"})


def _surface_class(rel: str, mode: str) -> str:
    """The detector-scoping class of a scanned file: 'pydoc' (a .py's docstrings),
    'served' (rendered .mjs/.html interface copy), 'profile' (a yaml), or 'law' (the
    two standing-law markdown files)."""
    if mode == "py":
        return "pydoc"
    if rel.endswith((".mjs", ".html")):
        return "served"
    if rel.endswith(".yaml"):
        return "profile"
    return "law"


# --- the tic lexicon ---------------------------------------------------------
# Each entry is (name, compiled regex, surface_classes). A match is one tic; a file's
# score is the sum of matches across every detector whose scope includes that file's
# surface class (``None`` = every surface).
_LEXICON: list[tuple[str, re.Pattern[str], frozenset[str] | None]] = [
    # "honest"/"honestly" as a virtue adverb-adjective. Hyphen-bound occurrences are
    # IDENTIFIERS, not virtue claims — the original term-of-art exemption (honest-empty)
    # generalised 2026-07-22 when doc-anchored ids (D-honest-status, the
    # demand-audit-floor-honest clause) tripped the prose ban from inside docstrings
    # (the G4 close; calibration named in the close commit, his to overrule).
    ("honest_adverb", re.compile(r"(?<!-)\bhonest(?:ly)?\b(?!-)", re.IGNORECASE), _ALL),
    # the "his word" formula — not the plural "his words" of quote attribution.
    ("his_word", re.compile(r"\bhis word\b", re.IGNORECASE), _ALL),
    # the "never the rule" formula.
    ("never_the_rule", re.compile(r"\bnever the rule\b", re.IGNORECASE), _ALL),
    # a run of 3+ consecutive ALL-CAPS words (>=2 letters each) — an incantation run.
    # Case-sensitive so genuine two-word acronym pairs (GET POST) never trip it.
    # Creative-Commons license identifiers (CC BY-NC-ND and family) are terms of
    # art, not emphasis — the same identifier exemption as honest-empty
    # (calibration 2026-08-07, his to overrule).
    ("allcaps_run",
     re.compile(r"\b(?!CC BY\b)(?<!CC )[A-Z]{2,}(?:[ -][A-Z]{2,}){2,}\b"), _ALL),
    # "the ONE" emphatic (article any case, ONE upper-case).
    ("the_one", re.compile(r"\b(?:[Tt]he|THE) ONE\b"), _ALL),
    # --- SERVED-SURFACE breach classes (W-register, 2026-07-22) -----------------
    # The wave regressions flooded the reader with build-internal tokens. These three
    # guard the rendered interface copy (.mjs/.html) only, so a docstring that cites a
    # path or id in prose is left alone.
    # sec:sN — a raw LaTeX section anchor shown as a UI label: the reader sees a build
    # id, not a section name (reason: raw ids above the fold are insider phrasing, P8).
    ("sec_label", re.compile(r"\bsec:s\d+\b"), _SERVED),
    # a full source module path (src/laplace/….py|.mjs|.html) rendered in served copy:
    # the surface names its own plumbing at the reader (reason: module paths in served
    # strings state mechanics to no one who can act on them, P8).
    ("module_path", re.compile(r"\bsrc/laplace/[\w/-]+\.(?:py|mjs|html)\b"), _SERVED),
    # a raw record/ruling id (PV-/RW-/PRM-/RM-/PRF-<digits>) shown above the fold:
    # provenance ids belong in the ledger, not the reader's face (reason: raw ids
    # above the fold, P8).
    ("raw_record_id", re.compile(r"\b(?:PV|RW|PRM|RM|PRF)-\d{6,}"), _SERVED),
]


def _score(text: str, surface: str = "served") -> tuple[int, dict[str, int]]:
    """Total tic count for a blob of text, plus the per-detector breakdown. Only
    detectors whose scope includes ``surface`` run (default 'served' runs them all)."""
    by_kind: dict[str, int] = {}
    for name, rx, scope in _LEXICON:
        if scope is not None and surface not in scope:
            continue
        n = len(rx.findall(text))
        if n:
            by_kind[name] = n
    return sum(by_kind.values()), by_kind


def _py_docstrings(path: Path) -> str:
    """Every module/class/function docstring in a .py file, joined. Comments are not
    reached (ast drops them); code string literals are deliberately not scanned — they
    are logic, not rule-bearing prose. A file that will not parse contributes nothing."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return ""
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                out.append(doc)
    return "\n".join(out)


def _whole_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _surface_files(root: Path) -> list[tuple[Path, str]]:
    """The scanned files as (path, mode) pairs; mode is 'py' (docstrings) or 'text'."""
    files: list[tuple[Path, str]] = []
    for rel in ("STANDING_LAW.md", "CLAUDE.md"):
        p = root / rel
        if p.is_file():
            files.append((p, "text"))
    for p in sorted((root / "profiles").rglob("*.yaml")):
        files.append((p, "text"))
    for p in sorted((root / "src" / "laplace").rglob("*.py")):
        files.append((p, "py"))
    ss = root / "src" / "laplace" / "web" / "static_shared"
    for pattern in ("*.mjs", "*.html"):
        for p in sorted(ss.glob(pattern)):   # top level only — no vendored subtrees
            files.append((p, "text"))
    return files


def scan(root: Path) -> dict[str, int]:
    """Per-file tic totals, keyed by repo-relative path (sorted, stable)."""
    counts: dict[str, int] = {}
    for path, mode in _surface_files(root):
        rel = str(path.relative_to(root))
        text = _py_docstrings(path) if mode == "py" else _whole_text(path)
        total, _by = _score(text, _surface_class(rel, mode))
        counts[rel] = total
    return counts


def scan_detailed(root: Path) -> dict[str, dict[str, int]]:
    """Per-file per-detector breakdown, for the printed report."""
    detail: dict[str, dict[str, int]] = {}
    for path, mode in _surface_files(root):
        rel = str(path.relative_to(root))
        text = _py_docstrings(path) if mode == "py" else _whole_text(path)
        _total, by = _score(text, _surface_class(rel, mode))
        if by:
            detail[rel] = by
    return detail


def _load_baseline(root: Path) -> dict[str, int]:
    p = root / BASELINE_REL
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    files = data.get("files") if isinstance(data, dict) else None
    return {k: int(v) for k, v in files.items()} if isinstance(files, dict) else {}


def _write_baseline(root: Path, counts: dict[str, int]) -> Path:
    p = root / BASELINE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    banked = {k: v for k, v in sorted(counts.items()) if v}
    payload = {
        "note": ("register tic baseline (scripts/audit_register.py). THE BASELINE IS "
                 "DEAD: the register law is now ABSOLUTE ZERO (W-register, "
                 "PRM-20260721-register-zero), so this store holds no normalized stock — "
                 "an empty ``files`` map is the only clean state, and any tic is a breach."),
        "total": sum(banked.values()),
        "files": banked,
    }
    p.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                 encoding="utf-8")
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--update-baseline", action="store_true",
                    help="rewrite corpus_friction/register_baseline.json from the "
                         "current scan (use after a deliberate register change)")
    a = ap.parse_args(argv)
    root = a.root.resolve()

    counts = scan(root)
    detail = scan_detailed(root)

    if a.update_baseline:
        p = _write_baseline(root, counts)
        total = sum(counts.values())
        print(f"wrote {p.relative_to(root)} — {total} tic(s) across "
              f"{sum(1 for v in counts.values() if v)} file(s)")
        return 0

    baseline = _load_baseline(root)
    regressions: list[tuple[str, int, int]] = []
    for rel, n in sorted(counts.items()):
        base = baseline.get(rel, 0)
        if n > base:
            regressions.append((rel, base, n))

    total = sum(counts.values())
    flagged = sorted((rel for rel, n in counts.items() if n), key=str)
    for rel in flagged:
        kinds = ", ".join(f"{k}={v}" for k, v in sorted(detail.get(rel, {}).items()))
        print(f"  {rel}: {counts[rel]} ({kinds})")

    # The baseline store is dead (zeroed — no normalized stock): the register law is
    # ABSOLUTE ZERO now, not at-or-below a banked count. Any tic is a breach and exits
    # nonzero — whether it reads as an above-(zero-)baseline regression or, defensively,
    # simply as a nonzero total. Exit 0 only at a genuine corpus-wide zero.
    if total > 0:
        if regressions:
            print(f"REGISTER BREACH: {len(regressions)} file(s) carry tic(s) "
                  "(baseline is zero — the law is absolute):")
            for rel, base, n in regressions:
                print(f"  {rel}: {n} tic(s)")
        else:
            print(f"REGISTER BREACH: {total} tic(s) across {len(flagged)} file(s) "
                  "(absolute zero required)")
        return 1
    print(f"register audit: OK (total=0 — absolute zero across "
          f"{len(counts)} scanned file(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
