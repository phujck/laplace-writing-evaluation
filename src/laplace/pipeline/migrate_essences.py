"""Essence hygiene migration (the author's ruling, 2026-07-08): migrate now,
zero prose changes.

Framing directives baked into node essences leak into prose (S2 rendered "not
the organising object" / "not the paper's organising principle" verbatim from
``def:staircase``). The split this module performs: the physics fact stays in
the essence, neutrally phrased; the POSITIONING DIRECTIVE moves to the node's
``projection.framing`` slot (set-projection merge), where the brief renderer
carries it on the POLICY channel only.

Three mechanical tiers, all DATA:

- ``FLAG_PATTERNS`` — clear builder-facing directives (capitalised claim-scoping
  emphasis, "demoted", meta-references to the paper's organising structure,
  spine/act placement, imperatives aimed at a writer). A hit flags the node.
- ``UNCERTAIN_PATTERNS`` — emphasis or artefact references that read as physics
  or provenance as often as directive. A hit without a flag hit is listed under
  ``uncertain`` and left alone (the conservative rule: when in doubt, exclude).
- ``DECISION_PREFIXES`` — goal:/flag:/fork: namespaces are the plan's own
  decision layer; their essences are rulings by nature, never flagged.

The rewrites are curated in ``SPLITS`` (audited data, not generation): apply()
refuses a flagged node with no reviewed split, so a future ledger change that
introduces a new directive fails loudly instead of being auto-rewritten.

The sibling migration ``migrate_plan_meta`` decomposes the 17-item legacy
``meta.builder_contract`` into the typed plan-meta fields (schema.PLAN_META_TYPED)
through ONE storyboard.plan_write set-meta op — through the L2 ledger, never a
hand-edit of the plan JSON.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import datetime as _dt
import json
import re
from pathlib import Path

from laplace.research import corpus_ingest as ci
from laplace.pipeline import ledger, registry
from laplace.pipeline.schema import proj_of

EVOLUTION_ID = "essence_hygiene_2026-07-08"
BY = "essence-hygiene-2026-07-08"

# ---------------------------------------------------------------------------
# The audit rule — patterns are data; tune here, never in the walkers
# ---------------------------------------------------------------------------

FLAG_PATTERNS: dict[str, tuple[re.Pattern, ...]] = {
    # meta-reference to the artefact's organisation ("the paper", "the disclosure")
    "organising-meta": (
        re.compile(r"not the (?:paper'?s\s+)?organising (?:object|principle)", re.I),
        re.compile(r"\bdemoted\b", re.I),
        re.compile(r"downstream readout among many", re.I),
    ),
    # imperatives aimed at a writer: how to state/present the content
    "writer-imperative": (
        re.compile(r"to be stated\b", re.I),
        re.compile(r"\bstated (?:carefully|positively|honestly|plainly)\b", re.I),
        re.compile(r"\bpresent\w*\s+s-primary\b", re.I),
        re.compile(r"\buse only where\b", re.I),
    ),
    # capitalised NOT as claim-scoping emphasis (what the prose may not claim)
    "claim-scoping-caps": (
        re.compile(r"does NOT claim"),
        re.compile(r"NOT (?:a limitation|an asymptotic)"),
    ),
    # positioning relative to the spine (the narrative chain is the plan's layer)
    "spine-positioning": (
        re.compile(r"\boff-spine\b", re.I),
        re.compile(r"RETIRED FROM (?:SPINE|PRIMARY MECHANISM)"),
        re.compile(r"RETRACTED FROM SPINE"),
        re.compile(r"not (?:the disclosure'?s|a) spine(?: driver)?\b", re.I),
    ),
    # narrative placement / rhetorical role (acts, hero/seal/headline figures)
    "narrative-placement": (
        re.compile(r"\bAct [1-3]\b"),
        re.compile(r"\bTHE (?:HERO|SEAL)\b"),
        re.compile(r"\bHEADLINE\b"),
        re.compile(r"the disclosure'?s headline", re.I),
    ),
}

UNCERTAIN_PATTERNS: dict[str, tuple[re.Pattern, ...]] = {
    # caps emphasis that reads as physics/logic (ONLY IF ..., NOT substructure)
    "caps-emphasis": (re.compile(r"\b(?:NOT|NEVER|ONLY)\b"), re.compile(r"\bCAUTION\b")),
    # lifecycle facts — provenance, not presentation
    "status-record": (re.compile(r"\bSUPERSEDED BY\b"),),
    # claim-landscape statements, declarative not imperative
    "claim-landscape": (re.compile(r"\bthe safe claim\b", re.I),),
    # machine-vocabulary placement references (spine-1, Beats 4)
    "machine-vocab-placement": (re.compile(r"\bspine-\d\b", re.I),
                                re.compile(r"\bBeats? \d\b")),
    # references to "the paper"/"the disclosure" (often the CITED paper, or the
    # result's own scope) and terminology notes the term registry already carries
    "artefact-reference": (re.compile(r"\bthe (?:paper|disclosure)\b", re.I),
                           re.compile(r"\bheadline (?:term|theorem)\b", re.I)),
    # goal-shaped imperatives (live inside the decision layer's own nodes)
    "goal-imperative": (re.compile(r"\bpresent (?:the invention|it|this) as\b", re.I),),
}

#: goal:/flag:/fork: are the decision layer — essences there ARE rulings.
DECISION_PREFIXES = ("goal:", "flag:", "fork:")


def flag_hits(text: str) -> list[str]:
    return [f"{cls}:{p.pattern}" for cls, pats in FLAG_PATTERNS.items()
            for p in pats if p.search(text or "")]


def uncertain_hits(text: str) -> list[str]:
    return [f"{cls}:{p.pattern}" for cls, pats in UNCERTAIN_PATTERNS.items()
            for p in pats if p.search(text or "")]


# ---------------------------------------------------------------------------
# The reviewed splits — object stays physics, framing gets the directive
# ---------------------------------------------------------------------------

SPLITS: dict[str, dict[str, str]] = {
    "def:staircase": {
        "object": (
            r"The staircase is a derived response channel of the spectral surface: "
            r"$\mu_\tau(s) = s + \frac{1}{2\tau}\,\partial_s \log Z_\tau(s)$ "
            r"(target-relative $H_\tau(s) = \mu_\tau(s) - T$). As $s$ sweeps isolated "
            r"spectral clusters $\mu_\tau(s)$ sticks near the locally dominant cluster "
            r"energy and steps between clusters; in the high-$\tau$ regime this is the "
            r"staircase surface. It is the most legible response surface read off "
            r"$Z_\tau(s)$, one channel among $\{\mu_\tau, \sigma_\tau^2, \kappa_m\}$."),
        "framing": (
            "Position the staircase as a derived readout of the spectral surface - one "
            "response channel among many, never the organising object and never the "
            "paper's organising principle."),
    },
    "fig:N11-window": {
        "object": (
            "DATA figure (double col, 2 panels): max-t S_vN and chi_req vs J per n in "
            "{8,10,12} under V_XXZ; entangling turns on at the per-n disc edge and "
            "persists across the window. Chi is flat in n at this scale, so the panel "
            "carries no hardness claim of its own (hardness scaling is settled by "
            "fig:N14-hardness-scaling). Generator N11_window.py."),
        "framing": ("Deliberately claims no hardness here - the hardness verdict "
                    "belongs to fig:N14-hardness-scaling. Act 3 opener."),
    },
    "fig:f4-within-window": {
        "object": (
            "PREAMBLE FIGURE F4 - within-window cluster substructure: the protocol's "
            "C-shaped extraction advantage. Two-panel side-by-side contrast. LEFT (V=0): "
            "exactly g(T_0)=5 degenerate eigenvalues at T_0, wide filter (1/sqrt(tau)), "
            "flat featureless mu_tau(lambda) inside cluster. RIGHT (V != 0): the 5 "
            "degeneracies split into perturbed sub-eigenvalues E_alpha^pert spread over "
            "Schur window of width ~||V||^2/Gamma_S; narrow filter 1/sqrt(tau) ~ "
            "||V||^2/Gamma_S; mu_tau(lambda) shows 5 sharp inflection peaks (detected: "
            "5/5); weight-conservation note sum p_alpha^pert = g(T_0)/2^n boxed (the "
            "Fork D negative result on totals, not substructure). Top caption: 'V != 0 "
            "lifts the degeneracy; the inflections of mu_tau(lambda) recover the g(T_0) "
            "sub-eigenvalues at polynomial shot cost, while classical methods need "
            "Omega(2^n) basis enumeration.' CLAIMS BACKED: (i) bounded V splits the "
            "cluster while preserving cluster locations to Weyl O(||V||) - kato-1995 "
            "(perturbation theory for linear operators), bhatia-1997 (matrix "
            "perturbation); (ii) Schur window width 1/sqrt(tau) ~ ||V||^2/Gamma_S - "
            "block-perturbation analysis (kato-1995 sec. III); (iii) mu_tau inflections "
            "decode sub-eigenvalues - the protocol's own within-window observable "
            "derivation (ref:free-snacks Eqs. 27-30, plus "
            "thm:c-shaped-staircase-extraction-advantage); (iv) classical-hardness "
            "contrast - subset-sum decision-problem complexity bounds "
            "(howgrave-graham-joux-2010, bonnetain-2020); (v) total-weight conservation "
            "on totals - direct first-order perturbation theory + Fork D resolution. "
            "PROVENANCE: script `F4_within_window.py` + tikz `F4_within_window.tex`. "
            "5 iteration cycles: (1) kwarg fix, (2) layout/spacing, (3) brace/label "
            "collisions, (4) repositioned conservation box for brace clearance, "
            "(5) converged."),
        "framing": "The headline figure of the preamble - iterated hardest.",
    },
    "fig:N15-planted-escape": {
        "object": (
            "DATA figure (double col, 2 panels): (a) planted-block chi = 4/8/16/30 ~ "
            "2^(n/4) at J=0.2/L (readability verified, worst spread 0.413 < 0.5) vs "
            "generic control pinned at chi=2 at identical (n,J,t); (b) planted S_vN "
            "fans out on the Jt clock, generic oscillates at the ln 2 floor exactly as "
            "Theorem A predicts. Generator N15_planted_escape.py."),
        "framing": "The seal - Act 3 coda / outlook.",
    },
    "fig:N14-hardness-scaling": {
        "object": (
            "DATA figure (double col, 2 panels): the hardness verdict measured from "
            "both sides across the ED wall (open=ED, filled=TEBD, dashed wall at n=13). "
            "(a) the whole fixed-J window family collapsed to one min-max band flat at "
            "chi in {2,3,4} n=8->20, zero cap hits; probe diamonds lift off only at "
            "J >= 1 (J=3: chi 6/6/11). (b) same in S_vN. Caption carries the "
            "sensing-grade sentence. Generator N14_hardness_scaling.py."),
        "framing": "Act 3.",
    },
    "fig:F-window-verdict": {
        "object": (
            "DATA figure (double col, 1 panel, twin axis - justified, the join is the "
            "content): S_vN(J) per n x measured fingerprint separation at K=1e5, with "
            "the shaded operating window [disc edge 0.023, escape 0.11] and J* = 0.05 "
            "marked. Inside the band: entangling and fingerprint above noise - "
            "goal:window-hunt resolved non-empty. Key accuracy at J* carried by the "
            "caption; both edges classically computable dial settings. Generator "
            "F_window_verdict.py."),
        "framing": "The hero figure - Act 3.",
    },
    "fig:N12b-decoder": {
        "object": (
            "DATA figure (double col, 2 panels): per-target integer hit-rate vs total "
            "shots (makes the 8-trial-median budget honest), V_XX and V_XXZ; three "
            "readouts of the same measurements (continuous -> integer snap -> "
            "+trial-median: 27-37% -> 86-100% at 8e5); K=infinity column 100% all "
            "families under the feasibility window + erasure. Generator N12b_decoder.py."),
        "framing": "Act 2.",
    },
    "fig:N13-fingerprint-jdial": {
        "object": (
            "DATA figure (double col, 2 panels): (a) sigma^2 ~ J^2.00 (V_XXZ) vs J^3.98 "
            "(V_XX) with slope triangles; g=1 identically zero stated as text; escape "
            "ceiling annotated. (b) measured separation vs J at K=1e3/1e4/1e5 - 2.1-2.5x "
            "at K=1e5 for J<=0.05, gone by 0.15. The F32 restatement's evidence. "
            "Generator N13_fingerprint_jdial.py."),
        "framing": "Act 2.",
    },
    "fig:N1r-retention-frontier": {
        "object": (
            "DATA figure (double col, 2 panels): (a) m-bar ~ n^2.6 parallel power laws "
            "per tau; (b) the collapse m-bar ~ 3.7||H||sqrt(tau) - the Nyquist law off "
            "the data; the n=12 tick-up dissolved as instance-luck. Caption carries the "
            "DP-price honesty. Generator N1r_retention_frontier.py on figstyle."),
        "framing": "Act 2.",
    },
    "fig:N12-identities": {
        "object": (
            "DATA figure (single col): the T6 staircase algebra holding to numerical "
            "floor across every dial and family - dH identity ~1e-6-1e-4 "
            "(grid-differencing limited), route-AB redundancy ~1e-12 (quadrature "
            "limited), tau-dial subset-exactness exactly zero (stated in text); "
            "interacting V_XXZ on the same floor as V=0 - the ruler does not care what "
            "it measures. Generator N12_identities.py on figstyle."),
        "framing": "Act 1: the ruler is exact.",
    },
    "res:half-depth-symmetric-branches": {
        "object": (
            r"$\langle\psi(T/2)|\psi(-T/2)\rangle=\langle\psi|e^{+iHT}|\psi\rangle"
            r"=G(-T)$. A symmetric two-branch implementation reaches signal time $T$ "
            r"with branch depth $T/2$: a coherence-/branch-depth reduction (and cleaner "
            r"organisation of systematic phase errors). The gain is a constant factor "
            r"in the architecture - the wall-clock accounting need not improve, so it "
            r"is not an asymptotic complexity gain."),
        "framing": ("State the half-depth gain carefully as a constant-factor "
                    "architectural gain, never as an asymptotic complexity miracle."),
    },
    "res:answer-key-certificate": {
        "object": (
            "Benchmark/verification mode of the disclosure: for known V, every value "
            "of the measured surface H(lambda, tau) has an exact classical answer key "
            "- DP for the V=0 lattice content plus the perturbation series for the "
            "V-dressing - while reproducing the measured family classically has no "
            "shortcut only for interacting V (irf:free-fermion-trap-quadratic-v; V_XXZ "
            "is the minimal hardware-native choice). The residual surface H_dev - "
            "H_key localises device error per energy window and per filter width: "
            "decoherence rounds steps (fake tilt), miscalibration displaces plateaus, "
            "leakage adds phantom plateaus. Amended post-smoke (2026-07-02): the "
            "original verify-in-energy/pay-in-time decoupling is false - pinned "
            "eigenvectors bound entanglement uniformly in t, so key-accuracy and "
            "hardness trade against each other in J. The mode lives in the J-window of "
            "goal:window-hunt if that window is non-empty (kill condition otherwise). "
            "Epistemic class: certification under trusted physics, not adversarial "
            "proof-of-quantumness; still ahead of deployed volume-law benchmarks "
            "(shallow-Clifford or heuristic XEB)."),
        "framing": ("State the epistemic class honestly - certification under trusted "
                    "physics, never adversarial proof-of-quantumness."),
    },
    "irf:sparse-target-visibility-fundamental": {
        "object": (
            "Boundary of the observable (T5 v3 reframe, 2026-07-01). For g(T) = 1 "
            "sparse-target instances, Var[Delta] = 0 identically over a single-point "
            "solution set - the T5 v3 primary observable (sigma^2 excess ratio) "
            "vanishes structurally and does not read sparse cases. This is a scope "
            "statement rather than a limitation: classical DP handles polynomial-weight "
            "sparse subset-sum in polynomial time, so the sparse regime is classically "
            "polynomial and there is no quantum claim to beat there. T5 v3 does not "
            "claim quantum sparse detection; the claim is efficient inference of "
            "density in poly-g and moderate-g regimes via the sigma^2 excess. The "
            "theory identifies which regimes carry the advantage (poly and moderate g) "
            "and where it does not apply (sparse g=1). N4/N8 in v5 verify the boundary "
            "empirically (sigma^2 excess = 0 on constructed sparse)."),
        "framing": ("An honest boundary, stated positively: a scope statement, never a "
                    "limitation of the disclosure."),
    },
    "irf:hierarchical-bit-bias-reduction": {
        "object": (
            "Speculative extension (T5.5). For structured multi-solution instances "
            "where the solution set has biased bit statistics (e.g., bit i takes value "
            "1 in >= 90% of solutions), the mean shift under V = J X_i (single-body) "
            "reads (2 <x_i>_{s(x)=T} - 1) * J^2/a_i whose sign directly reads the bias. "
            "Under NN reference V, the analogous measurement reads pair-state bias of "
            "(x_i, x_{i+1}). Iterative bit-fixing (measure bias, fix bit, reduce to "
            "(n-1)-bit problem, recurse) gives poly K on structured instances. "
            "Collapses on random-random solution sets (bit averages ~ 0.5, no confident "
            "bias) and does not cross the sparse boundary (T5.4). Scope: structured "
            "multi-solution instances, heuristic advantage."),
        "framing": ("Speculative, off-spine (T5.5): worth an IRF as a speculative "
                    "extension, never the disclosure's spine."),
    },
    "irf:repulsion-dominated-by-spread-second-order": {
        "object": (
            "Z-form second-order algebra (2026-07-01 T5 pass): direct target-miss "
            "centroid repulsion O(||V||^2 / n) is dominated by spread O(||V||^2 * "
            "n^{k/2}) by factor n^{1+k/2} (T3 Step 1-3). The original framing 'the "
            "wider-filter-via-repulsion mechanism fails' applied to a Z-form "
            "inter-cluster question that T5 shows is not the disclosure mechanism; the "
            "correct mechanism lives H-form inside the target window "
            "(irf:support-in-window-via-level-repulsion). Accurate physics ruling out "
            "one candidate mechanism (Z-level inter-cluster repulsion) so future "
            "readers do not attempt that route. Full derivation and retraction section "
            "in source/theory/T3_repulsion_analysis.md."),
        "framing": ("Retracted from spine (2026-07-01 T5 pass) - preserved off-spine "
                    "as a physics footnote documenting the ruled-out route."),
    },
    "irf:staircase-position-reading-of-perturbed-eigenvalues": {
        "object": (
            "H_tau(lambda) staircase transitions do mark eigenvalue positions, and "
            "reading positions is polynomial per Prop 3A. But reading individual "
            "sub-eigenvalue positions requires tau sharp enough to resolve "
            "intra-cluster spacings, which is a heavier resource requirement than the "
            "mechanism needs. T5 v3's primary observable is the scalar sigma^2 excess "
            "(irf:moment-excess-poly-K-any-tau) at a wider tau, which integrates the "
            "cluster's shape into a single number and does not require intra-cluster "
            "resolution. This record describes what the perturbed staircase looks like "
            "structurally (the physical picture); it is not the load-bearing "
            "observable."),
        "framing": ("Retired from primary mechanism (2026-07-01 T5 v3 pass; was the "
                    "v2 primary). Retained as narrative, off-spine."),
    },
    "irf:support-in-window-via-level-repulsion": {
        "object": (
            "T5 v1's primary mechanism rested on a misunderstanding of m_bar "
            "(Gauss-Hermite order vs retention count). The physical picture described "
            "here - V spreading g(T)-fold-degenerate mass into a window of resolvable "
            "sub-eigenvalues - remains correct as a description of the perturbation's "
            "effect on the spectrum. The load-bearing mechanism, however, is staircase "
            "position reading of the perturbed eigenvalues via H_tau(lambda) = "
            "N_tau/Z_tau (see irf:staircase-position-reading-of-perturbed-eigenvalues), "
            "not free-snacks bandwidth-bounded detection of Z magnitude within the "
            "window."),
        "framing": ("Retired from spine (2026-07-01 T5 v2 pass). Retained as "
                    "narrative, off-spine - never a spine driver."),
    },
    "res:t5-support-in-window-analysis": {
        "object": (
            "Superseded by res:t5v2-staircase-position-analysis (T5 v2 pass, "
            "2026-07-01); retained for provenance - documents the v1 attempt that "
            "conflated m_bar (Gauss-Hermite order) with the free-snacks retention "
            "count. The physical picture (V spreads g(T)-degenerate mass into "
            "sub-eigenvalues within a target-cluster window of bandwidth kappa_loc ~ "
            "g(T)) is correct as description, but the load-bearing mechanism is "
            "staircase position reading via H_tau(lambda), not bandwidth-bounded "
            "detection of Z. The v2 IRFs "
            "(irf:staircase-position-reading-of-perturbed-eigenvalues, "
            "irf:classical-mps-simulation-exp-cost) supersede the v1 drivers."),
        "framing": "Off-spine: superseded analysis retained for provenance.",
    },
    "res:t5v2-staircase-position-analysis": {
        "object": (
            "Superseded by res:t5v3-model-based-inference-analysis (T5 v3 pass, "
            "2026-07-01); retained for provenance - documents the v2 attempt that "
            "over-emphasised per-solution sub-eigenvalue position reading. The "
            "staircase-position-reading picture (H_tau(lambda) transitions mark "
            "eigenvalue positions) remains physically correct but is not the "
            "load-bearing observable per T5 v3; the primary observable is the sigma^2 "
            "excess ratio at wider tau, integrated over cluster shape."),
        "framing": "Off-spine: superseded analysis retained for provenance.",
    },
    "irf:density-profile-polynomial-K-at-V-zero": {
        "object": (
            "Path A. At V=0, ITQDE with lambda-sweep reuse gives Z_tau(lambda) across "
            "the entire staircase from one overlap family via classical reweighting. "
            "Free-snacks polynomial-K theorem (McCaul 2025 §VI) applied to the "
            "profile, not a single point: for windows where the smoothed density "
            "rho_tau(T) = g(T)/2^n * (filter integral) is polynomial in n, "
            "Z_tau(lambda) is estimable at polynomial K with relative precision "
            "1/sqrt(K) x poly(n). Emptiness certification for windows where the "
            "density is sub-threshold is a byproduct: Z_tau < K^{-1/2} certifies no "
            "polynomial-density solutions."),
        "framing": "The disclosure's headline, Part I.",
    },
}


# ---------------------------------------------------------------------------
# The audit — over the CURRENT live essences, both sources
# ---------------------------------------------------------------------------

def _repo_root(repo_root: Path | str | None) -> Path:
    return Path(repo_root) if repo_root is not None \
        else source_tree()


def live_essences(project: str, repo_root: Path | str | None = None) -> dict[str, dict]:
    """node → {essence, source, node_kind} over BOTH sources: the ledger reduction
    (``friction_current`` over ``rewire_list``) and the built network
    (``corpus_network``, which also carries tex-born nodes and applies the
    edit-essence overlay to them). Retired nodes are not live."""
    rr = _repo_root(repo_root)
    out: dict[str, dict] = {}
    for r in ci.friction_current(ci.rewire_list(rr, project)):
        out[r["node"]] = {"essence": r.get("essence") or "",
                          "source": "ledger(friction_current)",
                          "node_kind": r.get("node_kind")}
    troot = ci.resolve_corpus(rr, project)
    net = ci.corpus_network(troot, repo_root=rr, name=project) if troot else {"nodes": {}}
    for nid, nd in (net.get("nodes") or {}).items():
        if proj_of(nd).get("retired"):
            continue
        if nid in out:
            if (nd.get("essence") or "") != out[nid]["essence"]:
                out[nid]["source"] += "+net-disagrees"   # surfaced, never silent
        else:
            out[nid] = {"essence": nd.get("essence") or "",
                        "source": "tex(corpus_network)",
                        "node_kind": nd.get("kind")}
    return out


def audit(project: str,
          repo_root: Path | str | None = None) -> list[dict]:
    """Flag live essences carrying directive markers. ``project`` is
    explicit-required (the reviewed ``SPLITS`` are keyed to a specific corpus's
    node ids — a silent ``subset-sum-itqde`` default was a genericity trap that
    could audit the wrong project). Conservative: only the
    FLAG_PATTERNS classes flag; UNCERTAIN_PATTERNS hits (and any hit inside the
    goal:/flag:/fork: decision layer) are listed with ``verdict='uncertain'``
    and left untouched."""
    rows: list[dict] = []
    for nid, info in sorted(live_essences(project, repo_root).items()):
        ess = info["essence"]
        fl, un = flag_hits(ess), uncertain_hits(ess)
        if not fl and not un:
            continue
        row = {"node": nid, "source": info["source"], "essence_now": ess,
               "markers": fl + un}
        if nid.startswith(DECISION_PREFIXES):
            row.update(verdict="uncertain", rationale=(
                "decision-layer namespace (goal:/flag:/fork:) - the essence is a "
                "ruling by nature, not prose substrate"))
        elif fl:
            split = SPLITS.get(nid) or {}
            row.update(verdict="flag",
                       object_part=split.get("object"),
                       framing_part=split.get("framing"),
                       rationale="clear builder-facing directive: " + "; ".join(fl))
        else:
            row.update(verdict="uncertain", rationale=(
                "emphasis/reference reads as physics or provenance as often as "
                "directive: " + "; ".join(un)))
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# The apply — one L1 transaction, freeze first, round-trip gate inside
# ---------------------------------------------------------------------------

class RoundTripError(RuntimeError):
    """Raised inside the transaction so a failed gate rolls the append back."""


def apply(project: str, audit_rows: list[dict],
          repo_root: Path | str | None = None, dry_run: bool = True) -> dict:
    rr = _repo_root(repo_root)
    proj = registry.resolve(project)
    if proj is None:
        return {"error": f"unknown project {project!r}"}
    flagged = [r for r in audit_rows if r.get("verdict") == "flag"]
    unsplit = [r["node"] for r in flagged
               if not r.get("object_part") or not r.get("framing_part")]
    if unsplit:
        return {"error": "flagged nodes with no reviewed split - refuse to "
                         "auto-rewrite", "nodes": unsplit}
    dirty = [r["node"] for r in flagged if flag_hits(r["object_part"])]
    if dirty:
        return {"error": "an object_part still matches a flag pattern", "nodes": dirty}

    l1 = proj.path(proj.ledger, rr)
    evo = proj.path(proj.evolutions_dir, rr) / EVOLUTION_ID
    plan = {"project": project, "evolution": EVOLUTION_ID, "dry_run": dry_run,
            "flagged": len(flagged),
            "nodes": [r["node"] for r in flagged]}
    if dry_run:
        return plan

    # live state must still match the audited state (no drift between audit+apply)
    now = live_essences(project, rr)
    stale = [r["node"] for r in flagged
             if now.get(r["node"], {}).get("essence") != r["essence_now"]]
    if stale:
        return {"error": "live essence drifted since the audit - re-audit", "nodes": stale}

    before_bytes = l1.read_bytes()
    before = {"live_nodes": len(now), "ids": set(now)}
    frozen = ledger.freeze([l1], evo / "_freeze", label="pre_migration")

    with ledger.transaction(l1, by=BY, note="essence hygiene: object/framing split"):
        for r in flagged:
            res = ci.rewire_add(rr, project, {
                "kind": "edit-essence", "node": r["node"],
                "value": r["object_part"], "by": BY})
            if not res.get("ok"):
                raise RoundTripError(f"edit-essence rejected for {r['node']}: {res}")
            res = ci.rewire_add(rr, project, {
                "kind": "set-projection", "node": r["node"],
                "value": {"framing": r["framing_part"]}, "by": BY})
            if not res.get("ok"):
                raise RoundTripError(f"set-projection rejected for {r['node']}: {res}")

        # -- the round-trip gate (inside the transaction: a failure rolls back) --
        after = live_essences(project, rr)
        if set(after) != before["ids"] or len(after) != before["live_nodes"]:
            raise RoundTripError("live node-id set changed under the migration")
        troot = ci.resolve_corpus(rr, project)
        net = ci.corpus_network(troot, repo_root=rr, name=project)
        for r in flagged:
            if flag_hits(after[r["node"]]["essence"]):
                raise RoundTripError(f"{r['node']} essence still carries a flag marker")
            fr = proj_of(net["nodes"].get(r["node"]) or {}).get("framing")
            if fr != r["framing_part"]:
                raise RoundTripError(f"{r['node']} framing slot not populated")
        if not l1.read_bytes().startswith(before_bytes):
            raise RoundTripError("L1 is no longer a byte-suffix append")

    verdict = {"project": project, "evolution": EVOLUTION_ID, "verdict": "PASS",
               "freeze": str(frozen),
               "before": {"live_nodes": before["live_nodes"]},
               "after": {"live_nodes": len(after)},
               "migrated": [r["node"] for r in flagged],
               "checks": ["node-id set unchanged", "node count unchanged",
                          "flagged essences marker-free", "framing slots populated",
                          "L1 strict byte-prefix append"]}
    evo.mkdir(parents=True, exist_ok=True)
    (evo / "ROUNDTRIP.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=1), encoding="utf-8")
    return verdict


# ---------------------------------------------------------------------------
# The sibling: decompose the legacy builder_contract into typed plan meta
# ---------------------------------------------------------------------------

#: 1-based contract item → destination (the decomposition ruling, 2026-07-08).
#: Dropped items name the home that already carries them (CONTRACT_HOMES).
CONTRACT_DECOMPOSITION = {
    1: ("drop", "gate/structural: the brief IS the bundle (dispatch compiler + "
                "one-line contract carry it)"),
    2: ("drop", "glossary gate (gate_refs) + term registry carry both halves; "
                "GLOSSARY.md carries the SSG naming"),
    3: ("drop", "citations gate + brief boilerplate carry it"),
    4: ("drop", "retired-node exclusion is mechanical (renderer + validator)"),
    5: ("drop", "figures gate + brief caption boilerplate carry it"),
    6: ("postures", "per-node-kind"),
    7: ("voice_refs", None),
    8: ("workflow_modes", None), 9: ("workflow_modes", None),
    10: ("workflow_modes", None), 11: ("workflow_modes", None),
    12: ("workflow_modes", None), 13: ("workflow_modes", None),
    14: ("drop", "meta.body_lock_order already carries the sequencing as typed data"),
    15: ("drop", "naming lives in the term registry (GLOSSARY.md + meta.naming_gate)"),
    16: ("postures", "per-claim"),
    17: ("workflow_modes", None),
}

GATE_REFS = ["glossary", "citations", "figures", "connectivity", "meta_leak"]


def build_set_meta_value(meta: dict) -> dict:
    """The typed set-meta value from the live plan meta — items move VERBATIM,
    identified by position (guarded by a leading-keyword spot check)."""
    contract = meta.get("builder_contract") or []
    if len(contract) != 17:
        raise ValueError(f"expected the 17-item wall, found {len(contract)}")
    heads = {8: "DEFINE-BEFORE-USE", 12: "EVOLUTIONARY REPROJECTION",
             16: "EXACTNESS GRADING", 17: "MINIMAL-DIFF PRIOR"}
    for i, head in heads.items():
        if not contract[i - 1].startswith(head):
            raise ValueError(f"contract item {i} moved - expected {head!r}")
    modes = [contract[i - 1] for i in sorted(CONTRACT_DECOMPOSITION)
             if CONTRACT_DECOMPOSITION[i][0] == "workflow_modes"]
    postures = {CONTRACT_DECOMPOSITION[i][1]: contract[i - 1]
                for i in sorted(CONTRACT_DECOMPOSITION)
                if CONTRACT_DECOMPOSITION[i][0] == "postures"}
    voice_refs = ([meta["voice"]] if meta.get("voice") else []) + \
        [contract[i - 1] for i in sorted(CONTRACT_DECOMPOSITION)
         if CONTRACT_DECOMPOSITION[i][0] == "voice_refs"]
    return {"workflow_modes": modes, "postures": postures,
            "voice_refs": voice_refs, "gate_refs": list(GATE_REFS),
            "builder_contract": None, "voice": None}


def migrate_plan_meta(project: str,
                      repo_root: Path | str | None = None,
                      dry_run: bool = True) -> dict:
    """ONE storyboard.plan_write set-meta op (merge semantics; null values blank
    the legacy keys, which the brief renderer treats as absent). Through the L2
    ledger — the plan JSON is never hand-edited."""
    proj = registry.resolve(project)
    plan = proj.read_plan(_repo_root(repo_root)) if proj else None
    if plan is None:
        return {"error": f"no plan for project {project!r}"}
    value = build_set_meta_value(plan.get("meta") or {})
    if dry_run:
        return {"dry_run": True, "op": {"kind": "set-meta", "value": value}}
    from laplace.manuscript import storyboard
    res = storyboard.plan_write(project, {"kind": "set-meta", "value": value,
                                          "by": BY})
    return {"ok": res.get("ok"), "validation": res.get("validation"),
            "rebuild_class": res.get("rebuild_class"), "value": value}


# ---------------------------------------------------------------------------
# Banking — the evolutions dir is the audit trail
# ---------------------------------------------------------------------------

def bank_audit(project: str, rows: list[dict],
               repo_root: Path | str | None = None,
               plan_meta: dict | None = None) -> Path:
    rr = _repo_root(repo_root)
    proj = registry.resolve(project)
    evo = proj.path(proj.evolutions_dir, rr) / EVOLUTION_ID
    evo.mkdir(parents=True, exist_ok=True)
    counts = {"live": len(live_essences(project, rr)),
              "flagged": sum(1 for r in rows if r["verdict"] == "flag"),
              "uncertain": sum(1 for r in rows if r["verdict"] == "uncertain")}
    record = {"evolution": EVOLUTION_ID, "project": project,
              "ts": _dt.datetime.now().isoformat(timespec="seconds"),
              "counts": counts, "rows": rows}
    if plan_meta is not None:
        record["plan_meta"] = plan_meta
    (evo / "migration_plan.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return evo / "migration_plan.json"


if __name__ == "__main__":
    import sys
    live = "--apply" in sys.argv
    # back-compat CLI: a leading positional names the project; the historical
    # default stays subset-sum-itqde (the corpus the reviewed SPLITS target), but
    # it now lives HERE at the CLI boundary, not baked into the library defaults.
    project = next((a for a in sys.argv[1:] if not a.startswith("--")),
                   "subset-sum-itqde")
    rows = audit(project)
    fl = [r["node"] for r in rows if r["verdict"] == "flag"]
    un = [r["node"] for r in rows if r["verdict"] == "uncertain"]
    print(f"flagged {len(fl)}: {fl}")
    print(f"uncertain {len(un)}: {un}")
    if live:
        print(json.dumps(apply(project, rows, dry_run=False), indent=1))
        print(json.dumps(migrate_plan_meta(project, dry_run=False)["ok"], indent=1))
    else:
        print(json.dumps(apply(project, rows, dry_run=True), indent=1))
