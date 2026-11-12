"""test_playwright_walks_runner.py — the batch walks runner is honest, WITHOUT launching a browser.

`scripts/run_playwright_walks.py` (AUDIT_2026-07-15 §C3) discovers and batch-runs every
`tests/*.playwright.mjs`. That runner spawns real Chromium + a real scanner per walk, which is far
too heavy for pytest — so this suite exercises only the parts that DON'T touch a browser:

  (a) `--list` discovers ≥ 16 non-mutating walks on the live tree and names the anchor walks
      (j1_cold_open, parity_versions plain; j9_crank present but MARKED mutating) — the
      discovery is real, not a stub.
  (b) `--only` narrows the working set (scoped re-runs), both on the live tree via
      `--list --only` and via the importable filter directly.
  (c) the module exposes discovery as an importable function; it excludes anything that is not a
      `*.playwright.mjs` file (a bare `*.mjs`, a `.py`, a stray file), and — §C5 — it excludes
      the MUTATING_WALKS by default (include_mutating=True is the deliberate write-path door).

Pure stdlib, hermetic, sub-second: `--list` never runs a walk, and the exclusion tests run
against a tmp tree.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER = REPO_ROOT / "scripts" / "run_playwright_walks.py"

PLAIN_ANCHORS = ("j1_cold_open", "parity_versions")   # non-mutating, listed plainly
MUTATING_ANCHOR = "j9_crank"                          # §C5 — listed marked, excluded by default


def _load_module():
    """Import run_playwright_walks by path (it lives in scripts/, not on the default path)."""
    spec = importlib.util.spec_from_file_location("run_playwright_walks", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _plain_walk_lines(stdout: str) -> list[str]:
    """The unmarked enumeration lines — a marked mutating line does NOT end in .playwright.mjs."""
    return [ln for ln in stdout.splitlines() if ln.endswith(".playwright.mjs")]


# ── (a) --list discovers ≥ 16 non-mutating walks and names the anchors ─────────────────────────
def test_list_discovers_at_least_16_default_walks():
    proc = _run("--list")
    assert proc.returncode == 0, proc.stderr
    plain = _plain_walk_lines(proc.stdout)
    assert len(plain) >= 16, f"expected >= 16 non-mutating walks, got {len(plain)}:\n{proc.stdout}"
    # the count line trails the enumeration
    last = proc.stdout.strip().splitlines()[-1]
    assert "walks" in last, last


def test_list_names_the_anchor_walks():
    proc = _run("--list")
    assert proc.returncode == 0, proc.stderr
    plain = "\n".join(_plain_walk_lines(proc.stdout))
    for anchor in PLAIN_ANCHORS:
        assert anchor in plain, f"anchor walk {anchor} missing from --list:\n{proc.stdout}"


def test_list_marks_the_mutating_walk():
    proc = _run("--list")
    assert proc.returncode == 0, proc.stderr
    j9_lines = [ln for ln in proc.stdout.splitlines() if MUTATING_ANCHOR in ln]
    assert j9_lines, f"j9_crank missing from --list entirely:\n{proc.stdout}"
    assert all("mutating" in ln for ln in j9_lines), j9_lines
    # marked, therefore NOT part of the plain (default-run) enumeration
    assert not any(ln.endswith(".playwright.mjs") for ln in j9_lines), j9_lines


# ── (b) --only filters ─────────────────────────────────────────────────────────────────────────
def test_only_filters_the_working_set():
    proc = _run("--list", "--only", "parity_versions")
    assert proc.returncode == 0, proc.stderr
    plain = _plain_walk_lines(proc.stdout)
    assert plain, f"--only parity_versions matched nothing:\n{proc.stdout}"
    assert all("parity_versions" in ln for ln in plain), plain


def test_only_is_repeatable_or_combined():
    proc = _run("--list", "--only", "j1_cold_open", "--only", "parity_versions")
    assert proc.returncode == 0, proc.stderr
    plain = _plain_walk_lines(proc.stdout)
    assert any("j1_cold_open" in ln for ln in plain)
    assert any("parity_versions" in ln for ln in plain)
    assert all(("j1_cold_open" in ln or "parity_versions" in ln) for ln in plain)


def test_filter_walks_function_or_semantics():
    mod = _load_module()
    walks = [Path("tests/j1_cold_open.playwright.mjs"),
             Path("tests/j5_switch.playwright.mjs"),
             Path("tests/parity_versions.playwright.mjs")]
    assert mod.filter_walks(walks, None) == walks           # no filter → full set
    assert mod.filter_walks(walks, ["j5"]) == [walks[1]]    # single substr
    got = mod.filter_walks(walks, ["j1", "parity"])         # OR-combined
    assert got == [walks[0], walks[2]]


# ── (c) discovery is importable; excludes non-walks; §C5 excludes mutating by default ───────────
def test_discover_walks_is_importable_and_finds_real_walks():
    mod = _load_module()
    assert hasattr(mod, "discover_walks"), "module must expose discover_walks"
    walks = mod.discover_walks(REPO_ROOT)
    assert len(walks) >= 16
    names = {w.name for w in walks}
    for anchor in PLAIN_ANCHORS:
        assert any(anchor in n for n in names), f"{anchor} not discovered"


def test_default_discovery_excludes_the_mutating_walk():
    mod = _load_module()
    assert "j9_crank.playwright.mjs" in mod.MUTATING_WALKS
    default = mod.discover_walks(REPO_ROOT)
    assert not any(MUTATING_ANCHOR in w.name for w in default), \
        "j9_crank must be excluded from default discovery (§C5)"
    full = mod.discover_walks(REPO_ROOT, include_mutating=True)
    assert any(MUTATING_ANCHOR in w.name for w in full), \
        "include_mutating=True must include j9_crank"
    # the excluded set is exactly the MUTATING_WALKS registry — not a hardcoded one
    # (wave05_ladder_bank joined j9_crank in Wave 0.5; the registry is the truth)
    assert len(full) == len(default) + len(mod.MUTATING_WALKS)


def test_discover_walks_excludes_non_playwright_mjs(tmp_path):
    mod = _load_module()
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "jX_real.playwright.mjs").write_text("// a walk\n")
    (tests / "jY_also.playwright.mjs").write_text("// another walk\n")
    (tests / "j9_crank.playwright.mjs").write_text("// the mutating walk (§C5)\n")
    (tests / "store.mjs").write_text("// a plain module, NOT a walk\n")           # bare .mjs
    (tests / "helper.playwright.js").write_text("// wrong extension\n")           # .js not .mjs
    (tests / "test_something.py").write_text("# a pytest file\n")                 # .py
    (tests / "notes.playwright.mjs.bak").write_text("// backup, not a walk\n")    # .bak tail

    default = sorted(w.name for w in mod.discover_walks(tmp_path))
    assert default == ["jX_real.playwright.mjs", "jY_also.playwright.mjs"], default

    full = sorted(w.name for w in mod.discover_walks(tmp_path, include_mutating=True))
    assert full == ["j9_crank.playwright.mjs", "jX_real.playwright.mjs",
                    "jY_also.playwright.mjs"], full


def test_discover_walks_is_sorted():
    mod = _load_module()
    walks = mod.discover_walks(REPO_ROOT, include_mutating=True)
    assert walks == sorted(walks)
