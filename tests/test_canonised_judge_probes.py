"""Adversarial judge probes for THE CANONISED-REVIEW RUN (SSG whitepaper r3, 2026-07-10).

A fresh adversarial judge's refutation attempt against the run that ingested the
author's canonised hold-out review of the SSG whitepaper as a mixed prose+conceptric
run. Commits: 2d635ee (authorization) . bc966a6 (TC1/TC2/CL2 + free-snacks cites) .
b5c4a0d (comment routing) . 4847505 (prose lane) . e0622a4 (structural lane) .
71d0176 (finalize + RATIFY) . 561937e (evidence bundle). Pre-run baseline: bbdf571.

Every probe here is GREEN on the committed tree: the passing ones LOCK a verified
claim of the run; the voice probe LOCKS the one finding (the AO1 abstract introduced a
house-style semicolon, worsening laplace_verify voice 2->3 and contradicting the run's
"voice PASS" claim).

Read-only on source + manuscript. These tests add nothing to the pipeline; they pin the
run's own artefacts against its RATIFY.md / report claims.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WP = "synthetics papers/subset-sum-itqde/manuscript/whitepaper"
BASE = "bbdf571"   # pre-run baseline (legD-branding: invert the cringe seal)
RUN = "71d0176"    # canonised-run finalize + RATIFY
N_FILES = ["N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "NA1", "NA2", "NA3"]

# The r3 whitepaper corpus subtree (ssg-whitepaper-2026-07-10-r3.aux/.log, the
# descaffolded N-files' r3 label/tic placement) is absent from tree AND HEAD; the
# descaffold (r3 -> r4) is folded in. These probes pin that superseded r3 state,
# so they are banked known-fails on the C5.7 quiet-tree triage (2026-07-13).
_banked_r3 = pytest.mark.xfail(
    reason="absent whitepaper corpus subtree - banked known-fail 2026-07-13",
    strict=False,
)

_MATH_ENVS = r"equation\*?|align\*?|gather\*?|multline\*?|eqnarray\*?|displaymath"
_MATH_BLOCK = re.compile(r"\\begin\{(" + _MATH_ENVS + r")\}(.*?)\\end\{\1\}", re.DOTALL)
_MATH_BRACKET = re.compile(r"\\\[(.*?)\\\]", re.DOTALL)


def _rev_present(rev: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{rev}^{{commit}}"],
                          cwd=REPO, capture_output=True).returncode == 0


# RETIREMENT-BY-XFAIL (2026-07-22, W-TRIAGE; WO-20260717-163649-walk-retirement's sibling
# discipline for the pytest net): the canonised-review run's commits — the pre-run baseline
# BASE and the finalize RUN, and every commit named in this file's header between them — were
# squashed out of history by the branch rebase (claude/eigen-engine-instrument-*), so
# `git show BASE/RUN:...` no longer resolves (verified: git cat-file -e fails on both). The
# probes' whole SUBJECT — the byte-identity of that specific 2026-07-10 SSG canonised run over
# BASE..RUN — is UNREACHABLE. Matching this file's own `_banked_r3` idiom, a probe that needs
# an absent run-commit is a BANKED KNOWN-FAIL (xfail, non-strict), never a hard red nor a
# silent delete: the assertions are preserved verbatim so the coverage stays documented, and
# they re-arm the day the run's artefacts are re-anchored to commits that live in history.
_RUN_COMMITS_PRESENT = _rev_present(BASE) and _rev_present(RUN)
_ABSENT_RUN = ("canonised-run commits (BASE %s / RUN %s) absent from history after the branch "
               "rebase — the run's subject is unreachable (banked known-fail, W-TRIAGE 2026-07-22)"
               % (BASE, RUN))


def _git_show(rev: str, relpath: str) -> str:
    """Blob text at a revision (permanent in history; no worktree needed)."""
    if not _RUN_COMMITS_PRESENT:
        pytest.xfail(_ABSENT_RUN)
    out = subprocess.run(
        ["git", "show", f"{rev}:{relpath}"],
        cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, f"git show {rev}:{relpath} failed: {out.stderr}"
    return out.stdout


def _display_math(text: str) -> list[str]:
    return ([m.group(0) for m in _MATH_BLOCK.finditer(text)]
            + [m.group(0) for m in _MATH_BRACKET.finditer(text)])


# ---------------------------------------------------------------------------
# PROBE 1 — MARKER INTEGRITY (the unforgivable class)
# ---------------------------------------------------------------------------

def test_plan_and_nodes_markers_byte_identical_over_the_run():
    """% PLAN: / % NODES: lines byte-identical bbdf571..71d0176 in every N/App file."""
    for f in N_FILES:
        old = [l for l in _git_show(BASE, f"{WP}/{f}.tex").splitlines()
               if re.match(r"^% (PLAN|NODES):", l)]
        new = [l for l in _git_show(RUN, f"{WP}/{f}.tex").splitlines()
               if re.match(r"^% (PLAN|NODES):", l)]
        assert old == new, f"{f}.tex: PLAN/NODES marker drift"
        assert old, f"{f}.tex: expected PLAN/NODES markers to exist"


def test_paragraph_markers_byte_identical_over_the_run():
    """Per-paragraph `% N..-p..` markers byte-identical (order + text) in every file."""
    for f in N_FILES:
        old = [l for l in _git_show(BASE, f"{WP}/{f}.tex").splitlines()
               if re.match(r"^% N", l)]
        new = [l for l in _git_show(RUN, f"{WP}/{f}.tex").splitlines()
               if re.match(r"^% N", l)]
        assert old == new, f"{f}.tex: paragraph-marker drift"


# ---------------------------------------------------------------------------
# PROBE 2 — THE PHYSICS AGAINST THE BRIEF (no equation changed; TC1/TC2 land)
# ---------------------------------------------------------------------------

def test_no_display_math_changed_over_the_run():
    """The run's central physics claim: NO equation environment mutated (TC1/TC2 are
    prose+cite edits only). Every display-math block byte-identical bbdf571..71d0176."""
    for f in N_FILES:
        assert _display_math(_git_show(BASE, f"{WP}/{f}.tex")) == \
               _display_math(_git_show(RUN, f"{WP}/{f}.tex")), \
               f"{f}.tex: a display-math block changed (equation mutation)"


def test_tc1_bridge_sentences_and_free_snacks_cites_present():
    """TC1 landed as the brief prescribes: the Plancherel-Rotach / Gauss-Hermite bridge
    in N3, the m-bar = quadrature-truncation-budget naming in N4, and the free-snacks +
    QDE cites where N4 previously had zero."""
    n3 = _git_show(RUN, f"{WP}/N3.tex")
    n4 = _git_show(RUN, f"{WP}/N4.tex")
    assert "Plancherel-Rotach bulk form of the Gauss-Hermite quadrature" in n3
    assert "bulk Gauss-Hermite quadrature weight of the Gaussian aperture" in n3
    assert "Gauss-Hermite quadrature-truncation budget" in n4
    assert "super-exponentially convergent" in n4
    # N4 cited NEITHER key pre-run; both are present post-run.
    assert _git_show(BASE, f"{WP}/N4.tex").count("mccaul2025snacks") == 0
    assert _git_show(BASE, f"{WP}/N4.tex").count("leamer2024emulation") == 0
    assert "mccaul2025snacks" in n4 and "leamer2024emulation" in n4
    # both keys are real bib entries (fix was cite-only, no conceptric mint).
    bib = _git_show(RUN, f"{WP}/references.bib")
    assert "@article{mccaul2025snacks," in bib
    assert "@article{leamer2024emulation," in bib


def test_tc2_minimal_fix_matches_the_single_time_convention():
    """TC2 minimal fix per brief sec 3b: the inserted cumulant factor corrected to the
    single-time (-it_k)^m of Eq(10)/(11) as written, the doubled-time convention named
    as a bridge, and the contradictory 'This changes ...' flipped to 'does not change'."""
    old_n3 = _git_show(BASE, f"{WP}/N3.tex")
    new_n3 = _git_show(RUN, f"{WP}/N3.tex")
    # pre-run: the wrong insertion factor + the contradictory sentence.
    assert "(-2it_k)^{m}" in old_n3
    assert "This changes what the device must record." in old_n3
    # post-run: corrected insertion factor as the READ factor, and the reversal.
    assert "inserting classical factors $(-it_k)^{m}$" in new_n3
    assert "This does not change what the device must record." in new_n3
    assert "This changes what the device must record." not in new_n3
    # the doubled-time convention is named (where (-2it_k)^m IS right), not silently dropped.
    assert "doubled node time $2t_k$" in new_n3


def test_tc2_doubled_time_fork_is_banked_with_the_brief_cited():
    """The recommended-direction (doubled-time rewrite of Eq(10)/(11)) is BANKED for the
    author in the run RATIFY, with the physics brief cited — not silently taken."""
    ratify = _git_show(
        RUN, f"{WP}/evolutions/canonised-run_2026-07-10-r3/RATIFY.md")
    assert "BANKED PROMINENTLY" in ratify
    assert "freesnacks_hermite_brief.md" in ratify
    assert "doubled-time" in ratify


# ---------------------------------------------------------------------------
# PROBE 3 — THE CITES resolve (no undefined citation in the r3 log)
# ---------------------------------------------------------------------------

@_banked_r3
def test_r3_log_has_no_undefined_citation():
    log = (REPO / WP / "ssg-whitepaper-2026-07-10-r3.log").read_text(
        encoding="utf-8", errors="ignore")
    assert re.search(r"Citation.*undefined", log) is None
    bbl = (REPO / WP / "ssg-whitepaper-2026-07-10-r3.bbl").read_text(
        encoding="utf-8", errors="ignore")
    assert "{mccaul2025snacks}" in bbl and "{leamer2024emulation}" in bbl


# ---------------------------------------------------------------------------
# PROBE 4 — AO1 abstract + AO2/AO3 REAL tables (the hold-out's exact complaint)
# ---------------------------------------------------------------------------

def test_ao1_abstract_present_with_every_required_element():
    main = _git_show(RUN, f"{WP}/main.tex")
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", main, re.DOTALL)
    assert m, "no abstract in main.tex"
    ab = m.group(1)
    # explicit element checks (input / output / exact+finite / validation / no-hardness)
    assert "real-time overlap signal" in ab
    assert "reconstructs the spectral surface" in ab
    assert "reuse is exact and bounded" in ab
    assert "finite" in ab and "envelope" in ab
    assert "proof-of-principle sizes" in ab
    assert "no asymptotic hardness and no quantum advantage" in ab
    assert "no quantum hardware data" in ab
    # baseline had no abstract at all.
    assert "\\begin{abstract}" not in _git_show(BASE, f"{WP}/main.tex")


@_banked_r3
@pytest.mark.parametrize("tab,label,tex_no", [
    ("tab_resource", "tab:resource", "I"),
    ("tab_manifest", "tab:manifest", "III"),
    ("tab_crosswalk", "tab:crosswalk", "IV"),
])
def test_ao2_ao3_tables_are_real_tabular_and_resolve(tab, label, tex_no):
    """AO2 resource table + AO3 manifest/crosswalk are REAL \\tabular tables with labels
    that resolve in the r3 .aux (Tables I / III / IV) — not prose paragraphs."""
    src = _git_show(RUN, f"{WP}/tables_tex/{tab}.tex")
    assert r"\begin{tabular}" in src
    assert (r"\label{%s}" % label) in src
    assert (r"\input{tables_tex/%s}" % tab) in _git_show(RUN, f"{WP}/main.tex")
    aux = (REPO / WP / "ssg-whitepaper-2026-07-10-r3.aux").read_text(
        encoding="utf-8", errors="ignore")
    assert (r"\newlabel{%s}" % label) in aux


# ---------------------------------------------------------------------------
# PROBE 5 — DISPOSITION HONESTY (ER items genuinely untouched)
# ---------------------------------------------------------------------------

def test_er5_decoder_erasure_sentence_is_byte_identical():
    """ER5 (where the decoder's erased steps live) is an author-fork QUEUED item; no
    landed prose answers it. The decoder-erasure CLAUSE is byte-identical over the run
    (only an unrelated trailing disclaimer sentence in the same paragraph was trimmed)."""
    clause = ("The integer decoder reported coverage and conditional accuracy under "
              "its erasure rule inside a nonempty measured operating window.")
    assert clause in _git_show(BASE, f"{WP}/N8.tex")
    assert clause in _git_show(RUN, f"{WP}/N8.tex")


def test_er_fit_range_sentence_untouched():
    """ER3 (fit-range robustness) sits at the N4 m-bar fit; only the quadrature naming +
    cite changed around it, the fitted-slope statement itself is byte-identical."""
    frag = "polynomial in $n$ with a fitted log-log slope near $2.5$"
    assert frag in _git_show(BASE, f"{WP}/N4.tex")
    assert frag in _git_show(RUN, f"{WP}/N4.tex")


def test_twenty_two_confirmations_authorized_by_the_anchor():
    ledger = (REPO / WP / "feedback/feedback.jsonl").read_text(encoding="utf-8")
    conf = [json.loads(l) for l in ledger.splitlines()
            if l.strip() and '"record": "confirmation"' in l
            and "RATIFY-holdout-r2-canonised-2026-07-10" in l]
    assert len(conf) == 22
    assert all(c.get("authorized_by") == "RATIFY-holdout-r2-canonised-2026-07-10"
               for c in conf)


def test_no_figure_generator_or_figure_env_changed():
    """Figures route to F31, untouched here: no figure/ asset or generator diff in the run."""
    if not _RUN_COMMITS_PRESENT:            # absent run commits — banked known-fail (see _git_show)
        pytest.xfail(_ABSENT_RUN)
    out = subprocess.run(
        ["git", "diff", "--stat", BASE, RUN, "--", f"{WP}/figures"],
        cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0
    assert out.stdout.strip() == "", f"figures changed: {out.stdout}"


# ---------------------------------------------------------------------------
# PROBE 9 — SCHEMA / ROUTING (comment kind routed; live ledger intakes clean)
# ---------------------------------------------------------------------------

def test_comment_kind_routes_to_none_and_ratification_field_removed():
    from laplace.pipeline import schema
    assert "comment" in schema.KIND_TO_WORK
    assert schema.KIND_TO_WORK["comment"] is None
    # the anchor was re-typed: record='ratification' removed, kind='comment' added.
    ledger = (REPO / WP / "feedback/feedback.jsonl").read_text(encoding="utf-8")
    anchor = [json.loads(l) for l in ledger.splitlines()
              if l.strip() and "RATIFY-holdout-r2-canonised-2026-07-10" in l
              and '"id": "RATIFY-holdout-r2-canonised-2026-07-10"' in l]
    assert len(anchor) == 1
    assert anchor[0].get("kind") == "comment"
    assert anchor[0].get("status") == "resolved"
    assert "record" not in anchor[0]


def test_intake_over_the_live_ledger_raises_nothing():
    from laplace.pipeline import propagate as prop, registry, ledger as _led
    src = registry.resolve("subset-sum-itqde")
    recs = _led.read_jsonl(REPO / src.feedback_ledger)
    plan = src.read_plan()
    items = prop.intake_items(recs, plan, {})  # must not raise on the live ledger
    assert isinstance(items, list) and items


# ---------------------------------------------------------------------------
# PROBE 6/8 — TIC + finalize claims reproduce on the committed r3 tree
# ---------------------------------------------------------------------------

@_banked_r3
def test_disclaimer_tic_total_after_descaffold_is_14():
    """The final-layer de-scaffolding RUN (r3 -> r4) superseded the 85 baseline (down
    from 87): the author's keep-once-per-class law drove the whole-doc disclaimer tic
    total to 14 - 4 body-canonical statements plus 10 in the AppC/annex homes left in
    place for the disclosure-crosslink bite. Locks the number the RATIFY reports."""
    from laplace.pipeline import tics
    wp = REPO / WP
    hits = tics.disclaimer_hits(tics._gather_manuscript_text(tics._resolve_target(wp)))
    assert sum(len(v) for v in hits.values()) == 14


def test_finalize_title_is_verbatim_and_pdftitle_agrees():
    fin = json.loads((REPO / WP / "release/finalize.json").read_text())
    assert fin["title"] == "Spectral Surface Generation"
    assert fin["title_check"]["title_agrees"] is True
    assert fin["title_check"]["pdftitle_agrees"] is True
    assert "subset-sum benchmark" in fin["pdf_keywords"]  # meaningful, not a filename slug


# ---------------------------------------------------------------------------
# PROBE 7 — the evidence bundle: shas valid, absents honest
# ---------------------------------------------------------------------------

def test_evidence_bundle_manifest_shas_valid_and_absents_honest():
    bundle = REPO / WP / "release/bundles/canonised-run-evidence-2026-07-10.zip"
    assert bundle.is_file()
    with zipfile.ZipFile(bundle) as z:
        man = json.loads(z.read("MANIFEST.json"))
        present = [m for m in man["members"] if m.get("present")]
        absent = [m for m in man["members"] if not m.get("present")]
        assert man["git_head"].startswith("71d0176")
        # every present member's recorded sha256 matches the zipped bytes.
        for m in present:
            assert hashlib.sha256(z.read(m["arcname"])).hexdigest() == m["sha256"]
        # absents carry an honest reason (single-agent run: no economics/transcript).
        assert absent and all(m.get("note") or m.get("reason") for m in absent)


# ---------------------------------------------------------------------------
# FINDING (locked green) — the AO1 abstract regressed the voice house-style gate
# ---------------------------------------------------------------------------

def test_FINDING_ao1_abstract_introduced_a_prose_semicolon_voice_violation():
    """FINDING: the run's report/RATIFY claim 'voice PASS', but the AO1 abstract the run
    added to main.tex carries a semicolon ('...banks the estimates; a classical layer
    ...'), a house-style violation the rest of the manuscript avoids (it uses ' - ').
    Baseline main.tex had NO abstract and NO prose semicolon; r3 does. laplace_verify
    voice worsens 2->3 and does NOT pass. This locks the regression."""
    base_main = _git_show(BASE, f"{WP}/main.tex")
    run_main = _git_show(RUN, f"{WP}/main.tex")
    # prose-line semicolons = non-comment lines carrying ';'
    def prose_semicolon_lines(text):
        return [l for l in text.splitlines()
                if ";" in l and not l.lstrip().startswith("%")]
    assert prose_semicolon_lines(base_main) == []          # baseline: none in prose
    ab = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", run_main, re.DOTALL)
    assert ab and ";" in ab.group(1)                        # r3 abstract: introduced one
    assert prose_semicolon_lines(run_main), "r3 main.tex should carry the new prose ';'"


def test_FINDING_laplace_verify_voice_does_not_pass_on_r3():
    """The named-tool corroboration of the finding: laplace_verify(voice) on the live SSG
    manuscript returns pass=False (the run claimed 'voice PASS'). Guarded so it skips if a
    later session has moved the manuscript off r3."""
    main = REPO / WP / "main.tex"
    if not main.is_file():
        pytest.skip("SSG main.tex not on disk")
    from laplace.pipeline import verify as _verify
    res = _verify.verify(str(main), ["voice"])
    if "banks the estimates;" not in main.read_text(encoding="utf-8"):
        pytest.skip("manuscript no longer at r3 abstract state")
    assert res["passed"] is False
    assert res["issue_count"] >= 3
