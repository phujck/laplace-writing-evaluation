"""Adversarial judge probes for the SSG invention disclosure (child project
ssg-disclosure, artefact ssg-disclosure-2026-07-10-r1).

A FRESH judge banked these as PASSING regression guards. They encode the true
state found when refuting the disclosure against its technical backing, the
whitepaper r3 (ssg-whitepaper-2026-07-10-r3). They are STATIC + git only: no
latexmk, no uv, deterministic and fast.

Crown result: the crosswalk's SECTION anchors are all accurate and the copied
identities match the whitepaper verbatim (no new claims), BUT five of the
crosswalk's fine-pointer labels are PHANTOM — they are conceptric node-ids that
were never emitted as \\label{} in the whitepaper body, so a reader cannot
resolve them. One of the five (res:integer-decoder) is introduced by the
disclosure itself and is not even in the whitepaper's own Appendix-C crosswalk.
These tests pin that finding so it cannot silently regress or be forgotten.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

# The descaffold (whitepaper r3 -> r4) is now folded into HEAD, so these probes —
# which pin the r3 backing via `git show HEAD:...` — no longer resolve: NA3.tex /
# tables_tex/tab_crosswalk.tex are gone from HEAD and the N2-N5 label placement
# moved. Banked as known-fail on the C5.7 quiet-tree triage (2026-07-13); the
# absent-whitepaper-corpus-subtree class. strict=False so a re-pin xpasses freely.
_banked_r3 = pytest.mark.xfail(
    reason="superseded whitepaper r3 corpus subtree — banked known-fail 2026-07-13",
    strict=False,
)

ROOT = Path(__file__).resolve().parents[1]


def _rev_present(rev: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{rev}^{{commit}}"],
                          cwd=str(ROOT), capture_output=True).returncode == 0


DISCLOSURE = ROOT / "synthetics papers" / "subset-sum-itqde" / "disclosure"
MAIN_TEX = DISCLOSURE / "main.tex"
CHECKLIST = DISCLOSURE / "patent_checklist.json"
WP = "synthetics papers/subset-sum-itqde/manuscript/whitepaper"

# Section-number -> committed whitepaper source file, from the r3 aux
# (sec:N2->II, sec:N3->III, sec:N4->IV, sec:N5->V).
SEC_FILE = {"III": "N3", "IV": "N4", "V": "N5"}

# The disclosure crosswalk (main.tex tab:disclosure-crosswalk), row by row:
# (element, claimed-section(s), [cited whitepaper labels]).
CROSSWALK = [
    ("Reusable acquisition record", ["IV"],
     ["def:iqm-ancilla-readout", "def:native-hardware-V",
      "res:bandwidth-grid", "res:aperture-resolution"]),
    ("Storage as a bounded record", ["IV"],
     ["def:record-architecture-three-tier", "res:one-sided-reconstruction"]),
    ("Post-acquisition selection of s", ["III"],
     ["def:classical-dial", "thm:fourier-reconstruction-identity",
      "res:lambda-sweep-reuse"]),
    ("Post-acquisition selection of tau", ["III", "IV"],
     ["def:classical-dial", "res:aperture-resolution",
      "irf:heat-kernel-scale-space"]),
    ("Reconstruction of Z", ["III"],
     ["thm:fourier-reconstruction-identity", "def:coefficient-update"]),
    ("Derived response channels", ["III"],
     ["thm:response-identities-s", "thm:natural-parameters-cumulants"]),
    ("Within-window ratio observables", ["IV"],
     ["def:within-window-ratio-observables", "irf:shared-bank-ratio-boundary"]),
    ("Observable branches", ["III", "IV"],
     ["def:observable-surfaces", "def:record-architecture-three-tier"]),
    ("Validation reference", ["V"],
     ["def:answer-key", "res:answer-key-certificate", "def:operating-window"]),
    ("Degeneracy cartography", ["V"],
     ["res:degeneracy-cartography-single-family", "res:integer-decoder"]),
    ("Fingerprint diagnostic", ["V"],
     ["def:multiplicity-fingerprint", "def:null-channel"]),
]

# Labels the crosswalk cites that are NOT defined as \label in the whitepaper r3
# body — conceptric node-ids that never became LaTeX labels. THE crown finding.
PHANTOM_LABELS = {
    "res:lambda-sweep-reuse",              # row 3; not even in a whitepaper comment
    "res:answer-key-certificate",          # row 9; in AppC + N5 PLAN comment only
    "res:degeneracy-cartography-single-family",  # row 10; AppC + N5 comment only
    "res:integer-decoder",                 # row 10; disclosure-INTRODUCED, not in AppC
    "def:multiplicity-fingerprint",        # row 11; AppC + N5 comment only
}


def _git_show(relpath: str) -> str:
    """Committed (r3-state) content of a whitepaper file. Pinned to HEAD so the
    probe judges the disclosure against the r3 backing it names, immune to the
    active de-scaffolding churn in the working tree."""
    out = subprocess.run(["git", "show", f"HEAD:{relpath}"],
                         cwd=str(ROOT), capture_output=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    return out.stdout


def _labels_in(text: str) -> set[str]:
    import re
    return set(re.findall(r"\\label\{([^}]*)\}", text))


def _nows(s: str) -> str:
    return "".join(s.split())


# ---------------------------------------------------------------------------
# 1. CROSSWALK — section anchors are all accurate (the load-bearing anchor)
# ---------------------------------------------------------------------------

@_banked_r3
def test_every_real_crosswalk_label_lives_in_its_claimed_section():
    """For each non-phantom cited label, the \\label is defined in exactly the
    whitepaper section the crosswalk assigns it to. This is the good half of the
    crown probe: the section anchors are all correct."""
    labels_by_file = {f: _labels_in(_git_show(f"{WP}/{f}.tex"))
                      for f in ("N2", "N3", "N4", "N5")}
    for element, secs, labels in CROSSWALK:
        allowed = {SEC_FILE[s] for s in secs}
        for lab in labels:
            if lab in PHANTOM_LABELS:
                continue
            where = {f for f, labs in labels_by_file.items() if lab in labs}
            assert where, f"[{element}] real label absent from whitepaper: {lab}"
            assert where & allowed, (
                f"[{element}] label {lab} is in {where}, "
                f"but the crosswalk claims section(s) {secs} -> {allowed}")


# ---------------------------------------------------------------------------
# 2. CROSSWALK — the phantom fine-pointer labels (THE finding, pinned)
# ---------------------------------------------------------------------------

@_banked_r3
def test_phantom_crosswalk_labels_are_undefined_in_whitepaper_r3():
    """FINDING (HIGH): the crosswalk caption promises each row points 'by the
    body's own stable object labels'. These five are cited in the table but are
    NOT defined as \\label anywhere in the whitepaper r3 body — a reader cannot
    resolve them. Pinned so the gap cannot be forgotten."""
    all_labels: set[str] = set()
    for f in ("N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8",
              "NA1", "NA2", "NA3"):
        all_labels |= _labels_in(_git_show(f"{WP}/{f}.tex"))
    still_defined = PHANTOM_LABELS & all_labels
    assert not still_defined, (
        "labels now resolve in the whitepaper — finding fixed, update this "
        f"probe: {sorted(still_defined)}")


@_banked_r3
def test_row10_degeneracy_cartography_has_no_resolvable_label():
    """FINDING (HIGH, worst row): row 10's ENTIRE label column is unresolvable —
    both cited labels are phantom, and res:integer-decoder is introduced by the
    disclosure (it is not in the whitepaper's own AppC crosswalk)."""
    all_labels: set[str] = set()
    for f in ("N3", "N4", "N5"):
        all_labels |= _labels_in(_git_show(f"{WP}/{f}.tex"))
    row10 = next(r for r in CROSSWALK if r[0] == "Degeneracy cartography")
    resolvable = [lab for lab in row10[2] if lab in all_labels]
    assert resolvable == [], (
        f"row 10 now has a resolvable label: {resolvable}")
    # res:integer-decoder is a disclosure-introduced phantom: present in the
    # disclosure crosswalk, absent from the whitepaper's own AppC crosswalk.
    appc = _git_show(f"{WP}/tables_tex/tab_crosswalk.tex")
    assert "res:integer-decoder" in MAIN_TEX.read_text(encoding="utf-8")
    assert "res:integer-decoder" not in appc


# ---------------------------------------------------------------------------
# 3. NO NEW CLAIMS — the load-bearing identities are copied verbatim
# ---------------------------------------------------------------------------

def test_core_identities_match_the_whitepaper_verbatim():
    """The disclosure's equations are the whitepaper's, not a strengthened
    restatement. Whitespace-normalised fragments of the reconstruction identity,
    the coefficient update, the grid spacing and the shot bound each appear in
    both documents."""
    disc = _nows(MAIN_TEX.read_text(encoding="utf-8"))
    n3 = _nows(_git_show(f"{WP}/N3.tex"))
    n4 = _nows(_git_show(f"{WP}/N4.tex"))
    # reconstruction identity (disclosure eq:reconstruction <-> thm:fourier-...)
    recon = _nows(r"e^{-t^{2}/(4\tau)}\,e^{ist}\,G(t)\,dt")
    assert recon in disc and recon in n3
    # coefficient c_k (eq:coefficient <-> def:coefficient-update)
    ck = _nows(r"e^{-t_k^{2}/(4\tau)}\,e^{ist_k}")
    assert ck in disc and ck in n3
    # bandwidth grid spacing (slash form shared by the disclosure and Sec. III)
    dt = _nows(r"\pi/(\sqrt{8}\,\|H\|)")
    assert dt in disc and dt in n3
    # shot bound uses the same coefficient norm C_{tau,s}^2 = sum |c_k|^2
    assert _nows(r"C_{\tau,s}^{2}=\sum_k|c_k(\tau,s)|^{2}") in disc
    assert _nows(r"C_{\tau,s}^2 = \sum_k |c_k(\tau,s)|^2") in n4


def test_disclosure_keeps_the_whitepaper_hedge_no_advantage_no_hardness():
    """The disclosure asserts no advantage/hardness the whitepaper does not —
    it carries the same explicit hedge, in its own words."""
    disc = _nows(MAIN_TEX.read_text(encoding="utf-8"))
    assert _nows("no asymptotic hardness and no quantum advantage") in disc
    assert _nows("not a claim of asymptotic advantage") in disc
    assert _nows("chosen for checkability, not for hardness") in disc


# ---------------------------------------------------------------------------
# 4. BACKING REV — single source of truth in the .tex, but a sidecar duplicate
# ---------------------------------------------------------------------------

REV = "ssg-whitepaper-2026-07-10-r3"


@_banked_r3
def test_backing_rev_is_the_sole_macro_in_the_tex_but_duplicated_in_json():
    """In the .tex the backing rev lives only in \\def\\wpartefact (good — the
    crosswalk/bib/prose all read the macro). BUT patent_checklist.json hard-codes
    a second, untested copy, so an r4/r5 bump is a TWO-place edit, not one."""
    tex = MAIN_TEX.read_text(encoding="utf-8")
    # exactly one literal occurrence in the tex, and it is the macro definition
    assert tex.count(REV) == 1
    assert (r"\def\wpartefact{" + REV + "}") in tex
    # the sidecar second copy (the coupling gap)
    chk = json.loads(CHECKLIST.read_text(encoding="utf-8"))
    assert chk["technical_backing"] == REV


# ---------------------------------------------------------------------------
# 5. SCOPE — the two commits touch only the disclosure dir + registry + tests
# ---------------------------------------------------------------------------

def test_commits_touch_no_whitepaper_figures_or_workflows():
    """Scope discipline: the disclosure commits changed no whitepaper, figure,
    manuscript or workflow file (no radioactive-trio contact)."""
    # RETIREMENT-BY-XFAIL (W-TRIAGE 2026-07-22): this scope probe diffs a specific commit range
    # (27b6413^..e70e8cc) that the branch rebase (claude/eigen-engine-instrument-*) squashed out of
    # history — `git diff` can no longer resolve them (verified: git cat-file -e fails on both). The
    # probe's whole SUBJECT (the disclosure commits' file-scope) is UNREACHABLE. Matching the sibling
    # discipline in test_canonised_judge_probes.py, an absent-commit scope probe is a BANKED KNOWN-FAIL
    # (non-strict xfail), never a hard red nor a silent delete: the assertions are preserved verbatim so
    # the coverage stays documented, and they re-arm the day the range is re-anchored to live commits.
    if not (_rev_present("27b6413") and _rev_present("e70e8cc")):
        pytest.xfail("disclosure scope commits 27b6413^..e70e8cc absent from history after the branch "
                     "rebase — the range is unreachable (banked known-fail, W-TRIAGE 2026-07-22)")
    out = subprocess.run(
        ["git", "diff", "--name-only", "27b6413^", "e70e8cc"],
        cwd=str(ROOT), capture_output=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    touched = [p for p in out.stdout.splitlines() if p.strip()]
    assert touched, "expected a non-empty file list"
    for p in touched:
        in_scope = (
            p.startswith("synthetics papers/subset-sum-itqde/disclosure/")
            or p == "src/laplace/pipeline/registry.py"
            or p == "tests/test_disclosure.py")
        assert in_scope, f"out-of-scope file touched by the disclosure commits: {p}"
        # explicit radioactive-trio guard
        assert "/whitepaper/" not in p
        assert not p.startswith(
            "synthetics papers/subset-sum-itqde/manuscript/figures/")
        assert not p.startswith(".claude/workflows/")
