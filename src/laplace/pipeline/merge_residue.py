"""merge_residue.py — fold the paragraph_plan model-read residue into the inherited skeleton.

WHY A SIBLING MODULE (not ``stage_store.py``). ``stage_store.py`` is the VIEW-DERIVER half of the
stage stores: it turns a per-paper conceptric ``net`` into store rows MECHANICALLY (model tokens
~zero, "the point of v2"), and its contract is *deterministic, model-free* (same net -> byte-
identical rows, the property the holdout gate rests on). This module is the reciprocal, and a
DIFFERENT concern: it consumes the fleet's MODEL-READ residue (the per-paragraph FORM abstractions
eight sonnet readers produced) and folds it onto the inherited paragraph_plan SKELETON, then
normalizes what the readers left non-uniform. Mixing a model-read fan-in into the model-free view
deriver would blur that clean line, so the two live apart — the merge REUSES ``stage_store``'s
namespacing primitives (``_validate_namespacing``) rather than re-implementing them.

THE INPUTS (per paper, under ``corpus_stores/paragraph_plan/``):
  * ``<paper_id>.jsonl``          — the inherited SKELETON (``import_inherited`` from the voice
    store): his real paragraph prose (``embed_text``) + file/char/sha256 provenance, every FORM
    field ``None``.
  * ``<paper_id>.residue.jsonl``  — the model-read ENRICHMENT: the SAME rows, the FORM residue
    filled, ``provenance.residue_read`` stamped.

THE MERGE (:func:`merge_residue`). EVERY residue row is validated against its skeleton row on the
four load-bearing invariants — ``row_id``, ``embed_text``, ``span_ref.char_start/char_end``,
``span_ref.sha256`` — byte-identical or the whole paper's merge is REFUSED with a named
:class:`ResidueDriftError` (a reader that mutated the skeleton it was handed is not trusted to have
read faithfully). The enriched canonical row takes the SKELETON as authoritative (its invariants
survive verbatim) and folds in only the residue's FORM fields + ``provenance.residue_read``.

The proven provenance the readers established, stamped as truth:
  * finding (a) — ``span_ref.offset_basis = "strip_latex(voice_corpus_ingest)"`` on EVERY row: the
    char offsets index the STRIPPED text, not the raw ``.tex`` (three readers reproduced the
    pipeline and matched byte-for-byte).
  * finding (c) — the spliced rows (:data:`DEFECTIVE_ROWS`) are marked ``defective`` and excluded
    from the gate: their ``embed_text`` glues passages from opposite ends of the paper (a chunker
    fault); their reader nulled all residue.

THE NORMALIZATION (design's uniform-FORM discipline), originals PRESERVED:
  * ``length_band`` recomputed uniformly for all rows as ``[200*(cc//200), +200]`` (mechanical,
    judge-checkable); the reader's original band is kept as ``length_band_read``.
  * ``role`` UNTOUCHED; a coarse ``normalized_role`` is added via :data:`ROLE_TAXONOMY` (every one
    of the readers' ~165 singleton-heavy slugs mapped to one of 15 coarse classes; nulls stay
    null). The mapping is auditable — :func:`role_taxonomy_document` writes it to disk so a judge
    can contest any slug->class call.

Determinism: no wall-clock, no randomness in the merge or the taxonomy — the same residue yields
byte-identical enriched rows forever. The gate (:func:`nearest_exemplar_gate`) is seeded.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from laplace.pipeline import stage_store

CORPUS_STORES = stage_store.CORPUS_STORES

#: The provenance the readers PROVED (finding a): a paragraph_plan row's ``span_ref.char_start`` /
#: ``char_end`` index the output of ``voice_corpus_ingest.strip_latex`` — the STRIPPED prose — not a
#: raw byte offset into the ``.tex`` file named in ``span_ref.file``. Stamped on every merged row so
#: a downstream reader can never mis-resolve the span against the raw source.
OFFSET_BASIS = "strip_latex(voice_corpus_ingest)"

#: The rows a reader found DEFECTIVE and nulled (finding c): the chunker spliced two passages from
#: opposite ends of the paper into one ``embed_text``, so the row carries no coherent paragraph to
#: abstract. Marked ``defective`` and EXCLUDED from the gate (a spliced row is worse than no row).
DEFECTIVE_ROWS: dict[str, str] = {
    "PP-cif-p0011": "spliced-by-chunker",
}

#: The FORM fields the model read supplies (design §2.1's paragraph_plan ``form``, minus the
#: mechanical ``char_count``/``paragraph_span`` the skeleton already carries). ``length_band`` is
#: folded then OVERRIDDEN by the uniform recompute (its reader value survives as ``length_band_read``).
RESIDUE_FORM_FIELDS = (
    "role", "connective_prev", "connective_next", "carries_math",
    "carries_figure", "proposition_shape", "detail_level", "length_band",
)


# --------------------------------------------------------------------------- #
# THE ROLE TAXONOMY — 165 reader-coined slugs -> 15 coarse, auditable classes
# --------------------------------------------------------------------------- #
#: Each reader coined its OWN role vocabulary (finding d): ~165 distinct slugs over 260 rows,
#: 126 of them singletons — unusable as a retrieval class directly. This coarse taxonomy folds
#: every slug into one of 15 classes derived from the ACTUAL slug set (not an a-priori scheme).
#: It is class -> [slugs] for readability; :func:`_build_slug_to_class` inverts it and asserts no
#: slug is claimed twice. A judge can contest any membership — the mapping is the artifact, written
#: to ``_role_taxonomy.json``. ``role`` itself is never mutated; only ``normalized_role`` is derived.
ROLE_TAXONOMY: dict[str, list[str]] = {
    "abstract-summary": [
        "state-conclusion-summary", "state-the-abstract", "summarise-contribution",
        "summarise-findings", "summarize-contribution", "summarize-the-contribution",
    ],
    "motivate-or-gap": [
        "contextualize-the-topic", "establish-context", "identify-the-gap",
        "motivate-approximation", "motivate-broad-context", "motivate-numerical-testbed",
        "motivate-the-gap", "motivate-the-problem", "motivate-the-scenario", "orient-the-field",
        "pose-a-research-question", "pose-research-question", "preempt-triviality-objection",
        "rebut-misconception", "state-the-obstacle", "state-the-paradox",
        "state-the-scaling-problem", "state-the-tension",
    ],
    "survey-prior": [
        "compare-to-related-method", "connect-background-to-system", "connect-to-related-work",
        "establish-background", "introduce-prior-technique", "review-background-theory",
        "review-prior-work", "situate-in-prior-work", "situate-the-method",
        "survey-prior-representations", "survey-prior-work", "survey-related-phenomena",
        "survey-special-cases",
    ],
    "state-contribution": [
        "state-paper-contribution", "state-the-approach", "state-the-contribution",
        "summarize-the-algorithm",
    ],
    "roadmap": [
        "orient-the-section", "outline-the-paper", "outline-the-structure", "roadmap",
        "roadmap-the-paper", "state-contribution-and-roadmap",
    ],
    "define-or-setup": [
        "calibrate-the-metric", "clarify-notation", "define-governing-relation",
        "define-key-concept", "define-notation", "describe-experimental-apparatus",
        "describe-sample-system", "describe-the-apparatus", "describe-the-procedure",
        "describe-the-samples", "establish-the-target-formalism", "frames-the-analysis",
        "gloss-notation-and-assumptions", "introduce-a-construction", "introduce-a-parameter",
        "introduce-example", "introduce-physical-example", "introduce-the-example",
        "introduce-the-example-system", "introduce-the-experiment", "introduce-the-setup",
        "set-up-the-experiment", "set-up-the-hamiltonian", "set-up-the-metric", "set-up-the-model",
        "set-up-the-objective", "sets-up-a-theorem", "setup-model", "specify-the-experiment",
        "specify-the-parameter-regime", "state-assumption",
        "state-empirical-tunability-and-define-term", "state-numerical-setup",
        "state-secondary-matching-constraint", "unpack-the-definition",
    ],
    "derive": [
        "characterize-the-optimisation", "close-the-derivation", "derive-a-relation",
        "derive-a-result", "derive-a-step", "derive-control-relation", "derive-existence-claim",
        "derive-step", "state-a-proof-sketch",
    ],
    "state-result": [
        "present-comparison-result", "quantify-the-result", "report-a-result", "report-experiment",
        "report-numerical-result", "report-the-result", "state-a-complexity-bound",
        "state-a-consequence", "state-a-result", "state-an-implication", "state-headline-result",
        "state-result", "state-the-central-result", "summarize-a-result",
        "summarize-the-method-and-result",
    ],
    "interpret": [
        "address-a-follow-up-question", "assert-the-benefits", "assess-experimental-feasibility",
        "close-with-reflection", "demonstrate-with-example", "explain-a-mechanism",
        "explain-physical-mechanism", "interpret-a-result", "interpret-and-continue",
        "interpret-derived-relation", "interpret-discrepancy", "interpret-result",
        "interpret-the-objective", "interpret-the-result", "justify-the-candidate",
        "reflect-on-a-property", "state-a-benefit", "state-benefit", "state-the-key-insight",
        "validate-approximation", "validate-the-method",
    ],
    "present-figure-data": [
        "present-figure-data", "present-figure-result",
    ],
    "compare-or-relate": [
        "draw-an-analogy", "draw-conceptual-analogy", "identify-a-correspondence", "state-a-mapping",
    ],
    "caveat-or-limitation": [
        "add-a-caveat", "mitigate-the-limitation", "note-a-gauge-freedom", "qualify-a-result",
        "state-a-limitation", "state-caveat-with-example", "state-limitation",
        "state-limitation-of-prior-work", "summarize-and-caveat",
    ],
    "extend-or-generalize": [
        "cite-applications", "conjecture-an-extension", "extend-the-method", "extend-the-setup",
        "generalize-a-result", "introduce-the-application", "propose-an-extension",
        "propose-applications", "review-applications", "sketch-application", "specialize-a-case",
        "speculate-a-connection",
    ],
    "future-work": [
        "close-with-future-work", "outline-future-work", "project-future-applications",
        "propose-future-work", "raise-open-questions", "sketch-future-work",
        "state-future-limitation", "state-outlook-extension",
    ],
    "acknowledge": [
        "acknowledge-funding", "acknowledge-support", "acknowledgments",
    ],
}


def _build_slug_to_class(taxonomy: dict[str, list[str]]) -> dict[str, str]:
    """Invert ``class -> [slugs]`` to ``slug -> class``, refusing any slug claimed by two classes
    (an ambiguous mapping is a taxonomy bug, caught here not at merge time)."""
    out: dict[str, str] = {}
    for cls, slugs in taxonomy.items():
        for s in slugs:
            if s in out:
                raise ValueError(
                    f"merge_residue: role slug {s!r} mapped to both {out[s]!r} and {cls!r}")
            out[s] = cls
    return out


#: The inverted, validated ``slug -> coarse class`` map — the authority :func:`normalized_role` uses.
SLUG_TO_CLASS: dict[str, str] = _build_slug_to_class(ROLE_TAXONOMY)
#: The coarse class names, sorted (stable order for the taxonomy document + any class enumeration).
ROLE_CLASSES: list[str] = sorted(ROLE_TAXONOMY)


def normalized_role(role: Optional[str]) -> Optional[str]:
    """Map a reader's fine-grained ``role`` slug to its coarse :data:`ROLE_CLASSES` class. ``None``
    stays ``None`` (a defective/unread row keeps its null). An UNKNOWN slug raises ``KeyError`` —
    the taxonomy is required to cover every slug in the data, so an unmapped slug is a loud failure,
    never a silent miscategorisation (design's auditable-mapping discipline)."""
    if role is None:
        return None
    if role not in SLUG_TO_CLASS:
        raise KeyError(
            f"merge_residue.normalized_role: role slug {role!r} is not in the taxonomy "
            f"(the taxonomy must cover EVERY slug; add it to ROLE_TAXONOMY)")
    return SLUG_TO_CLASS[role]


def uniform_length_band(char_count: Optional[int]) -> Optional[list[int]]:
    """The uniform, mechanical, judge-checkable length band for a paragraph of ``char_count`` chars:
    ``[200*(cc//200), 200*(cc//200)+200]`` (the convention two of the eight readers already used).
    ``None`` char_count -> ``None`` (no fabricated band)."""
    if char_count is None:
        return None
    lo = 200 * (int(char_count) // 200)
    return [lo, lo + 200]


def role_taxonomy_document() -> dict[str, Any]:
    """The auditable taxonomy artifact (written to ``_role_taxonomy.json``): the ``slug -> class``
    map a judge can contest, plus the readable ``class -> [slugs]`` grouping and the counts."""
    return {
        "schema": "paragraph-plan-role-taxonomy/0.1",
        "note": ("Coarse role taxonomy: each of the 8 sonnet readers coined its own role "
                 "vocabulary (~165 distinct slugs over 260 rows, 126 singletons). Every slug is "
                 "folded into one of 15 coarse classes DERIVED from the actual slug set. `role` is "
                 "never mutated; `normalized_role` is derived from `map` below. Every mapping is "
                 "contestable — this file is the audit surface."),
        "n_classes": len(ROLE_CLASSES),
        "n_slugs": len(SLUG_TO_CLASS),
        "classes": ROLE_CLASSES,
        "class_slugs": {cls: sorted(ROLE_TAXONOMY[cls]) for cls in ROLE_CLASSES},
        "map": {slug: SLUG_TO_CLASS[slug] for slug in sorted(SLUG_TO_CLASS)},
    }


# --------------------------------------------------------------------------- #
# THE SECTION-JOB TAXONOMY — 142 reader-coined `job` slugs -> 12 coarse classes
# --------------------------------------------------------------------------- #
#: The section_architecture readers coined a per-paper `job` slug for every section (143 distinct
#: over 147 rows, 139 singletons — the same singleton-heavy shape the paragraph `role` had, one
#: altitude up). This coarse taxonomy folds every slug into one of 12 classes DERIVED from the
#: actual slug set (a section-appropriate arc: introduce -> define -> derive -> bound -> demonstrate
#: -> apply -> interpret -> situate -> conclude -> outlook -> admin). `job` is never mutated; a
#: coarse `normalized_job` is derived and gated on. The map is the audit surface a judge can contest
#: — :func:`job_taxonomy_document` writes it to ``_job_taxonomy.json`` (the ``_role_taxonomy.json``
#: sibling for this store). Mirrors :data:`ROLE_TAXONOMY` exactly; the two never share a slug space.
JOB_TAXONOMY: dict[str, list[str]] = {
    "introduce-motivate": [
        "frame-the-decoherence-objection-and-preview-the-refutation",
        "frame-the-open-question-and-preview-the-result", "motivate-and-introduce-ERT",
        "motivate-and-outline", "motivate-and-pose-the-distinguishability-question",
        "motivate-and-pose-the-unitary-question", "motivate-and-preview",
        "motivate-and-preview-the-approach", "motivate-and-preview-the-correspondence",
        "motivate-hamiltonian-encoding-and-preview-the-paper",
        "motivate-itqde-and-preview-the-free-snack-thesis", "motivate-problem-and-introduce-SSMC",
        "motivate-relaxing-the-2pi-encoding-constraint", "motivate-the-gap-and-preview-the-paper",
        "motivate-the-irreversibility-puzzle", "motivate-the-non-uniqueness-question",
        "motivate-the-partition-free-approach", "motivate-the-problem-and-preview-the-argument",
        "survey-then-stake-the-gap",
    ],
    "define-setup-model": [
        "construct-the-KvN-hilbert-space-formalism",
        "construct-the-quantum-and-classical-influence-functionals",
        "construct-the-quenched-density-representation",
        "define-the-model-and-formalise-the-target", "define-the-model-and-success-criteria",
        "define-the-waveoperator-and-its-dynamics",
        "establish-the-CIF-as-the-SLEs-classical-limit",
        "establish-the-kvn-hilbert-space-formalism",
        "formalise-the-photonic-system-and-RC-pipeline",
        "specify-the-minimal-hamiltonian-encoded-reservoir-and-augment-it-with-delay-embedding",
    ],
    "derive-prove": [
        "assemble-the-explicit-matrix-elements-for-numerical-propagation",
        "characterise-when-wrapping-preserves-separability",
        "construct-the-entropic-master-equation-and-its-classical-limit",
        "derive-the-ERT-approximation", "derive-the-KvN-path-integral-in-full-detail",
        "derive-the-central-correspondence", "derive-the-central-result",
        "derive-the-classical-kvn-limit", "derive-the-closed-form-hmf-in-the-commuting-sector",
        "derive-the-explicit-boundary-condition-for-the-oscillator-and-free-particle",
        "derive-the-general-SSMC-field-construction-procedure",
        "derive-the-general-first-principles-SSMC-field-from-open-system-dynamics",
        "derive-the-hadamard-test-primitive", "derive-the-hubbard-stratonovich-identity",
        "derive-the-implicit-tracking-field-equation", "derive-the-influence-functional",
        "derive-the-noise-correlation-functions", "derive-the-non-uniqueness-condition",
        "derive-the-quantum-bouncer's-Airy-eigenbasis", "derive-the-quantum-unitary-mapping",
        "derive-the-stochastic-equations-of-motion", "derive-the-tracking-equation-of-motion",
        "identify-the-waveoperator-with-the-wigner-function",
        "introduce-bopp-operators-and-derive-their-dynamics",
        "prove-existence-and-uniqueness-of-the-tracking-field-solution",
        "prove-self-adjointness-implies-entropy-conservation", "prove-the-uniqueness-theorem",
        "purify-the-waveoperator-into-a-vector-state",
        "replicate-the-unitary-construction-in-the-classical-kvn-framework",
        "solve-the-driven-oscillator-equation-of-motion",
        "transform-the-oscillating-boundary-problem-into-the-mirror's-rest-frame",
    ],
    "bound-error-analysis": [
        "bound-the-largest-gap-itqde-can-stably-resolve-under-truncation",
        "define-the-model-metrics-and-derive-the-scaling-heuristic",
        "derive-and-bound-the-twinning-field",
        "derive-the-full-gauss-hermite-truncation-error-bound",
        "derive-the-full-ratio-variance-bound-underlying-the-sampling-error-claim",
        "derive-the-quadrature-truncation-error-bound",
        "derive-the-quadrature-truncation-that-linearizes-the-overlap-count",
        "derive-the-sampling-cost-bound-and-introduce-the-controlled-smoothing-tradeoff",
        "derive-the-shot-noise-error-bound",
        "fit-the-entropic-model-to-the-qBounce-data-and-bound-sigma",
        "generalize-the-model-and-quantify-the-infeasibility",
    ],
    "algorithm-estimator": [
        "develop-and-analyze-the-quantum-algorithm",
        "document-the-discretised-noise-generation-algorithm",
        "present-an-alternative-ancilla-free-estimator",
    ],
    "demonstrate-validate": [
        "apply-SSMC-to-molecular-mixtures-and-validate-numerically",
        "apply-SSMC-to-solid-state-systems-and-validate-numerically",
        "define-the-metric-and-demonstrate-the-enhancement", "demonstrate-ERT-outperforming-WMC",
        "demonstrate-cross-representation-nonlinearity", "demonstrate-the-method-numerically",
        "demonstrate-the-minimal-reservoirs-regression-synthesis-and-prediction-performance",
        "demonstrate-the-scaling-prediction-numerically",
        "demonstrate-wrapping-improves-regression-fit",
        "derive-and-benchmark-the-imaginary-time-correction",
        "derive-the-optical-mapping-and-validate-numerically",
        "numerically-demonstrate-non-uniqueness-and-its-work-cost",
        "specify-and-validate-the-noise-generation-scheme",
        "specify-the-chi-squared-fitting-procedure-over-the-free-parameters",
        "stress-test-the-basic-model-on-a-worked-example",
        "validate-simulations-via-ehrenfest-theorem", "validate-the-prediction-numerically",
    ],
    "apply-extend-generalize": [
        "adapt-the-free-fall-model-to-the-oscillating-mirror-apparatus",
        "apply-ESLE-to-the-driven-spin-boson-model",
        "extend-the-correspondence-to-spectral-estimation",
        "extend-the-demonstration-to-a-classification-task",
        "extend-the-mapping-to-dissipative-and-hybrid-evolutions",
        "generalize-the-single-mass-master-equation-to-arbitrary-mass",
        "sketch-the-finite-dimensional-spin-extension",
        "specify-the-generalised-hamiltonian-and-initial-conditions",
        "supplement-with-an-alternate-initial-condition-test",
    ],
    "interpret-explain": [
        "assess-experimental-feasibility", "exhibit-an-explicit-counterexample-state",
        "explain-the-Fourier-mode-mechanism-behind-the-gain",
        "interpret-nonconservation-as-quantum-tunneling",
        "interpret-the-result-and-probe-its-generality",
        "locate-itqdes-hidden-exponential-cost-within-the-qma-hardness-landscape",
    ],
    "situate-relate": [
        "contrast-the-entropic-model-against-the-Diosi-Penrose-spontaneous-collapse-family",
        "situate-the-correspondence-in-broader-theory", "situate-the-result-against-prior-work",
    ],
    "conclude-synthesise": [
        "recap-and-specialise-the-ESLE-formalism",
        "recapitulate-itqde-and-construct-the-spectral-staircase-estimator",
        "summarise-and-motivate-the-generalisation",
        "summarise-findings-and-discuss-experimental-feasibility",
        "summarize-and-restate-the-significance",
        "summarize-the-minimal-architecture-and-situate-it-within-broader-ml-trends",
        "synthesize-the-result-and-motivate-the-turbulence-alternative",
    ],
    "future-work-outlook": [
        "recapitulate-the-finding-and-project-applications",
        "situate-the-free-snack-result-in-a-renormalization-group-lens-and-project-applications",
        "situate-the-sigma-bound-against-the-Diosi-Penrose-model-and-project-implications",
        "summarise-results-and-outline-extensions", "summarize-and-open-future-directions",
        "summarize-and-project-future-work", "summarize-contributions-and-discuss-outlook",
        "synthesise-and-open-future-directions",
        "synthesise-implications-and-broaden-to-other-observables",
        "synthesise-results-and-project-extensions", "synthesise-results-and-scope-limitations",
        "synthesise-the-mechanism-and-scope-future-work", "synthesize-implications-and-extensions",
    ],
    "acknowledge-admin": [
        "acknowledge-contributors", "acknowledge-funding", "acknowledge-support",
        "attribute-author-contributions", "attribute-individual-author-contributions",
        "catalog-supplementary-content-and-acknowledgments", "declare-author-contributions",
        "declare-no-conflicts-of-interest", "disclose-conflicts-of-interest",
        "state-author-contributions", "state-data-and-code-availability",
        "state-data-availability", "state-data-availability-boilerplate",
    ],
}

#: The inverted, validated ``job slug -> coarse class`` map (reuses :func:`_build_slug_to_class`,
#: so a slug claimed by two classes fails loudly here, not at merge time).
JOB_SLUG_TO_CLASS: dict[str, str] = _build_slug_to_class(JOB_TAXONOMY)
#: The coarse section-job class names, sorted (stable order for the taxonomy doc + enumeration).
JOB_CLASSES: list[str] = sorted(JOB_TAXONOMY)


def _normalize_slug(slug: Optional[str], slug_to_class: dict[str, str], field: str) -> Optional[str]:
    """Map a reader-coined fine slug to its coarse class via ``slug_to_class``. ``None`` stays
    ``None`` (a null/defective row keeps its null). An UNKNOWN slug raises ``KeyError`` — the
    taxonomy MUST cover every slug in the data, so an unmapped slug is a loud failure, never a
    silent miscategorisation. The one primitive behind :func:`normalized_role` and
    :func:`normalized_job`."""
    if slug is None:
        return None
    if slug not in slug_to_class:
        raise KeyError(
            f"merge_residue: {field} slug {slug!r} is not in its taxonomy "
            f"(the taxonomy must cover EVERY slug; add it)")
    return slug_to_class[slug]


def normalized_job(job: Optional[str]) -> Optional[str]:
    """Map a section reader's fine ``job`` slug to its coarse :data:`JOB_CLASSES` class (the
    section_architecture gate class). ``None`` stays ``None``; an unknown slug raises ``KeyError``.
    The section-store twin of :func:`normalized_role`."""
    return _normalize_slug(job, JOB_SLUG_TO_CLASS, "job")


def job_taxonomy_document() -> dict[str, Any]:
    """The auditable ``_job_taxonomy.json`` artifact — the ``slug -> class`` map a judge can
    contest, the readable ``class -> [slugs]`` grouping, and the counts. Twin of
    :func:`role_taxonomy_document`."""
    return {
        "schema": "section-architecture-job-taxonomy/0.1",
        "note": ("Coarse section-job taxonomy: the section_architecture readers coined a per-paper "
                 "`job` slug for every section (143 distinct over 147 rows, 139 singletons). Every "
                 "slug is folded into one of 12 coarse classes DERIVED from the actual slug set. "
                 "`job` is never mutated; `normalized_job` is derived from `map` below and is the "
                 "gate class. Every mapping is contestable — this file is the audit surface."),
        "n_classes": len(JOB_CLASSES),
        "n_slugs": len(JOB_SLUG_TO_CLASS),
        "classes": JOB_CLASSES,
        "class_slugs": {cls: sorted(JOB_TAXONOMY[cls]) for cls in JOB_CLASSES},
        "map": {slug: JOB_SLUG_TO_CLASS[slug] for slug in sorted(JOB_SLUG_TO_CLASS)},
    }


# --------------------------------------------------------------------------- #
# the drift validation — a reader that mutated the skeleton is REFUSED
# --------------------------------------------------------------------------- #
class ResidueDriftError(ValueError):
    """Raised when a residue row has drifted from its skeleton on a load-bearing invariant
    (``row_id`` set, ``embed_text``, ``span_ref.char_start/char_end``, ``span_ref.sha256``). The
    whole paper's merge is refused — a reader that altered the prose/offsets it was handed is not
    trusted to have read faithfully."""


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def validate_residue_against_skeleton(
    paper_id: str, skeleton: list[dict[str, Any]], residue: list[dict[str, Any]],
) -> None:
    """Refuse ``paper_id``'s merge on ANY drift between residue and skeleton (the four named
    invariants). Raises :class:`ResidueDriftError` naming the paper + row + field; returns silently
    when every row is byte-identical on those invariants."""
    sk = {r["row_id"]: r for r in skeleton}
    res = {r["row_id"]: r for r in residue}
    if set(sk) != set(res):
        missing = sorted(set(sk) ^ set(res))
        raise ResidueDriftError(
            f"{paper_id}: residue/skeleton row_id sets differ (symmetric diff: {missing[:8]}"
            f"{'...' if len(missing) > 8 else ''}) — merge refused")
    for rid in sk:
        a, b = sk[rid], res[rid]
        if a["embed_text"] != b["embed_text"]:
            raise ResidueDriftError(
                f"{paper_id}/{rid}: embed_text drifted between skeleton and residue — merge refused")
        sa = (a.get("provenance") or {}).get("span_ref") or {}
        sb = (b.get("provenance") or {}).get("span_ref") or {}
        for field in ("char_start", "char_end", "sha256"):
            if sa.get(field) != sb.get(field):
                raise ResidueDriftError(
                    f"{paper_id}/{rid}: span_ref.{field} drifted "
                    f"({sa.get(field)!r} != {sb.get(field)!r}) — merge refused")


# --------------------------------------------------------------------------- #
# the merge — enriched canonical rows, provenance stamped, normalization applied
# --------------------------------------------------------------------------- #
def enrich_row(skeleton_row: dict[str, Any], residue_row: dict[str, Any]) -> dict[str, Any]:
    """Build ONE enriched canonical row: the SKELETON is authoritative (its invariants survive
    verbatim); the residue's FORM fields + ``provenance.residue_read`` are folded in; the proven
    provenance is stamped (``offset_basis``, ``defective``); the FORM is normalized (uniform
    ``length_band`` with the reader's original kept as ``length_band_read``; ``normalized_role``).
    Pure — mutates nothing the caller holds."""
    sk_form = skeleton_row.get("form") or {}
    res_form = residue_row.get("form") or {}
    role = res_form.get("role")
    char_count = sk_form.get("char_count")

    form = {
        "role": role,                                   # UNTOUCHED (the reader's slug)
        "normalized_role": normalized_role(role),       # coarse class; None stays None
        "connective_prev": res_form.get("connective_prev"),
        "connective_next": res_form.get("connective_next"),
        "carries_math": res_form.get("carries_math"),
        "carries_figure": res_form.get("carries_figure"),
        "proposition_shape": res_form.get("proposition_shape"),
        "detail_level": res_form.get("detail_level"),
        "length_band": uniform_length_band(char_count),  # RECOMPUTED uniformly
        "length_band_read": res_form.get("length_band"),  # the reader's original, preserved
        "char_count": char_count,                        # mechanical (from skeleton)
        "paragraph_span": sk_form.get("paragraph_span"),
    }

    prov = json.loads(json.dumps(skeleton_row.get("provenance") or {}))  # deep copy
    span = prov.setdefault("span_ref", {})
    span["offset_basis"] = OFFSET_BASIS                  # finding (a), on EVERY row
    res_read = (residue_row.get("provenance") or {}).get("residue_read")
    if res_read is not None:
        prov["residue_read"] = res_read

    enriched: dict[str, Any] = {
        "row_id": skeleton_row["row_id"],
        "embed_text": skeleton_row["embed_text"],       # his real prose, skeleton-authoritative
        "form": form,
        "provenance": prov,
    }
    reason = DEFECTIVE_ROWS.get(skeleton_row["row_id"])
    if reason is not None:
        enriched["defective"] = reason                  # finding (c)
    return enriched


# --------------------------------------------------------------------------- #
# THE FOUR-LENS GENERALIZATION — one merge over section/spine/derivation/figure
# --------------------------------------------------------------------------- #
# The paragraph_plan merge above is the PRECEDENT. The four mechanical-view stages
# (section_architecture / spine_chain / derivation_walk / figure_caption) share its exact spine —
# validate every residue row against its skeleton, fold ONLY what the reader was allowed to fill,
# write through the namespaced writer, consume — differing only in WHICH form fields the reader
# fills, what class the gate reads, whether a coarse taxonomy is derived, and which rows the fleet's
# converged CAVEAT LEDGER flagged. So the difference is DATA, captured in one :class:`StoreSpec` per
# store; :func:`merge_residue` dispatches on it. No merge logic is duplicated.
from dataclasses import dataclass, field as _dc_field  # noqa: E402


@dataclass(frozen=True)
class TaxonomySpec:
    """A coarse taxonomy folded over a fine per-paper slug field (design's auditable-mapping
    discipline). ``fine`` is the reader's slug (never mutated); ``normalized`` is the derived coarse
    class the gate reads; ``slug_to_class`` is the validated inversion; ``doc`` writes the audit
    artifact to ``file``."""
    fine: str
    normalized: str
    slug_to_class: dict[str, str]
    classes: list[str]
    file: str
    doc: Any                       # a zero-arg callable -> the taxonomy document dict
    index_key: str                 # the key the store's _index.json summarises the taxonomy under


@dataclass(frozen=True)
class StoreSpec:
    """Everything that makes one four-lens store's residue merge differ from another's — pure DATA.

    ``residue_form_fields``  the form keys the reader FILLED or REPLACED (a mechanical proxy the
                             reader overrode counts here); everything else in the row is a load-
                             bearing invariant the reader must return byte-identical (validated).
    ``gate_class_key``       the form key the holdout gate classes on (a closed vocab used directly,
                             or a derived ``normalized_*`` class).
    ``preserve_mechanical``  ``{skeleton_field: kept_as}`` — a mechanical proxy the reader overrode,
                             preserved for the audit (mirrors the paragraph ``length_band_read``).
    ``taxonomy``             a :class:`TaxonomySpec` when the gate class is a coarse fold of a fine
                             per-paper slug (section_architecture), else ``None`` (closed vocab).
    ``defective_rows``       ``{row_id: reason}`` — EXCLUDED from the gate (the ledger's dead /
                             truncated rows); ``caveat_rows`` — KEPT but flagged (residue sound).
    ``store_caveats``        the store-level caveats block for ``_index.json`` (the ledger's §(e)).
    """
    store: str
    residue_form_fields: tuple[str, ...]
    gate_class_key: str
    preserve_mechanical: dict[str, str] = _dc_field(default_factory=dict)
    taxonomy: Optional[TaxonomySpec] = None
    defective_rows: dict[str, str] = _dc_field(default_factory=dict)
    caveat_rows: dict[str, str] = _dc_field(default_factory=dict)
    store_caveats: dict[str, str] = _dc_field(default_factory=dict)
    #: An optional MECHANICAL defective detector ``(row) -> reason|None`` — the belt-and-suspenders
    #: beyond the named ``defective_rows`` list: it catches corrupted rows the fleet's converged
    #: ledger MISSED (e.g. figure_caption's brace-bug truncation reaches papers the ledger did not
    #: name). The named list wins on conflict (its reason is authoritative); the detector fills the
    #: rest. Its verdict is the source of truth for the gate — no corrupted row is gated on faith.
    defective_detector: Any = None


#: The mechanical signature of finding (b): a truncated caption's embed_text is (after stripping any
#: leading braces / \color{} noise) essentially a bare ``\label{...}`` fragment — the
#: ``\caption{\label{...}}`` brace bug captured only up to the label's closing brace.
_LABEL_FRAGMENT_RX = re.compile(r"^\s*(\{[^{}]*\}\s*)*\\label\{", re.IGNORECASE)


def looks_caption_truncated(embed_text: str) -> bool:
    """True iff ``embed_text`` is (essentially) only a ``\\label{...}`` fragment — the mechanical
    signature of finding (b)'s ``\\caption{\\label{...}}`` brace-bug truncation. A short caption that
    is real prose is NOT flagged; the detector keys on the label-fragment shape, not length alone."""
    return bool(_LABEL_FRAGMENT_RX.match(embed_text or ""))


def _detect_caption_truncated(row: dict[str, Any]) -> Optional[str]:
    """The figure_caption defective detector: flag a label-fragment ``embed_text`` as
    ``caption-truncated-mechanical`` (finding b). Catches truncated rows the converged ledger under-
    counted — the plain source of truth for what a corrupted caption is."""
    return "caption-truncated-mechanical" if looks_caption_truncated(row.get("embed_text", "")) else None


#: The section-job coarse taxonomy, packaged for the section_architecture spec.
_JOB_TAXONOMY_SPEC = TaxonomySpec(
    fine="job", normalized="normalized_job", slug_to_class=JOB_SLUG_TO_CLASS,
    classes=JOB_CLASSES, file="_job_taxonomy.json", doc=job_taxonomy_document,
    index_key="job_taxonomy")

#: The four-lens store specs — the caveat-ledger findings (a)-(e) live HERE as data.
FOUR_LENS_SPECS: dict[str, StoreSpec] = {
    # section_architecture — the reader replaced the mechanical `job` proxy with a per-paper fine
    # slug and filled arc/question_class. Gate on the coarse normalized_job. (c) span-overrun caveat.
    "section_architecture": StoreSpec(
        store="section_architecture",
        residue_form_fields=("job", "arc", "question_class"),
        gate_class_key="normalized_job",
        preserve_mechanical={"job": "job_mechanical"},
        taxonomy=_JOB_TAXONOMY_SPEC,
        caveat_rows={"SA-nuodfgnl-s4": "span-overrun"},          # finding (c)
        store_caveats={
            "prl_paragraph_bodies_absent": (
                "PRL-style \\paragraph{} run-in headers carry their body inline, which the section "
                "atomiser does not split into separate prose blocks — so some sections' embed_text "
                "and para_count under-represent the real paragraph structure "
                "(dynamical-generation-of-epsilon-near-zero-behaviour-via). The 3 unbridgeable "
                "papers (driven-imposters, polaron-imposters, superoscillations-superspectroscopy) "
                "carry NO inline \\section blocks at all and are absent from every store."),
            "section_label_may_grab_inner_label": (
                "span_ref.section_label is the section node's first \\label, which in a few papers "
                "is an equation/figure label sitting at the section head, not the section's own "
                "(super-sensing-100-fold-enhancement-in-thz-time-domain) — an audit handle there, "
                "not a resolvable section key."),
            "span_overrun": (
                "SA-nuodfgnl-s4 (non-uniqueness-of-driving-fields) has a char span overrunning to "
                "EOF, swallowing a commented-out appendix + bibliography — flagged per-row "
                "caveat:span-overrun. The residue FORM is sound; only mechanical char_end/para_count "
                "are inflated."),
        },
    ),
    # spine_chain — the reader replaced the mechanical num-dep `ladder_move` proxy with the faithful
    # move-class and filled claim/supports. Gate on ladder_move DIRECTLY (closed vocab). (d) + (e).
    "spine_chain": StoreSpec(
        store="spine_chain",
        residue_form_fields=("ladder_move", "claim_class", "supports_class"),
        gate_class_key="ladder_move",
        preserve_mechanical={"ladder_move": "ladder_move_mechanical"},
        caveat_rows={"SC-pfatoqsih-Single-Trajectory_Density_Matrix_Path_Integral": "rung-artifact"},
        store_caveats={
            "spine_elevation_flattening": (
                "the spine-elevation overlay flattens multi-step chains into a single stratum for "
                "optical-indistinguishability-twinning, so its rung/of_rungs ladder is shallower "
                "than the paper's true derivation depth."),
            "unresolved_eqref_dags": (
                "papers whose \\eqref labels do not resolve against atomised equation nodes yield "
                "near-empty derivation DAGs, so few/no rungs surface "
                "(decoherence-free-entropic-gravity-model-and-experimental)."),
            "rung_artifact": (
                "eq:Single-Trajectory_Density_Matrix_Path_Integral (partition-free) carries "
                "inconsistent rung data — a rung-0 base in its own row yet a dependency of rung-1 "
                "rows — flagged per-row caveat:rung-artifact (residue FORM sound)."),
        },
    ),
    # derivation_walk — the reader replaced the mechanical arity `step_kind` proxy with the faithful
    # step-class and filled granularity/elision/eq_env. Gate on step_kind DIRECTLY (closed vocab).
    "derivation_walk": StoreSpec(
        store="derivation_walk",
        residue_form_fields=("step_kind", "granularity", "elision", "eq_env"),
        gate_class_key="step_kind",
        preserve_mechanical={"step_kind": "step_kind_mechanical"},
        caveat_rows={"DW-pfatoqsih-Single-Trajectory_Density_Matrix_Path_Integral": "rung-artifact"},
        store_caveats={
            "unresolved_eqref_dags": (
                "papers whose \\eqref labels do not resolve against atomised equation nodes yield "
                "near-empty derivation DAGs, so few/no steps surface "
                "(decoherence-free-entropic-gravity-model-and-experimental)."),
            "rung_artifact": (
                "eq:Single-Trajectory_Density_Matrix_Path_Integral (partition-free) carries "
                "inconsistent rung data in the walk too — flagged per-row caveat:rung-artifact "
                "(residue FORM sound)."),
        },
    ),
    # figure_caption — the reader filled caption_move/figure_role/panels. Gate on figure_role
    # DIRECTLY (4 slugs, near-closed). (a) dead-commented + (b) caption-truncated rows are DEFECTIVE.
    "figure_caption": StoreSpec(
        store="figure_caption",
        residue_form_fields=("caption_move", "figure_role", "panels", "panel_labels"),
        gate_class_key="figure_role",
        defective_rows={
            # (a) DEAD COMMENTED-OUT source — extracted live from %-commented / duplicate-label blocks
            "FC-lra-errorsnodephasing": "dead-commented-source",
            "FC-qdei-convergence": "dead-commented-source",
            "FC-qdei-FH_rel_err": "dead-commented-source",
            "FC-mqrwhe-delays_example": "dead-commented-source",
            # (b) CAPTION TRUNCATED — \caption{\label{...}} brace bug captured only the label fragment
            "FC-upreev-setup": "caption-truncated-mechanical",
            "FC-upreev-pdf": "caption-truncated-mechanical",
            "FC-upreev-sinc": "caption-truncated-mechanical",
            "FC-upreev-freq": "caption-truncated-mechanical",
            "FC-upreev-freqmix": "caption-truncated-mechanical",
            "FC-upreev-spiral": "caption-truncated-mechanical",
            "FC-mqrwhe-delay-performance": "caption-truncated-mechanical",
            "FC-mqrwhe-delayANMSE": "caption-truncated-mechanical",
            "FC-mqrwhe-non-autonomous": "caption-truncated-mechanical",
            "FC-mqrwhe-timeseries": "caption-truncated-mechanical",
        },
        defective_detector=_detect_caption_truncated,   # catches the 4 mean-force rows the ledger missed
        store_caveats={
            "caption_truncated_mechanical": (
                "the \\caption{\\label{...}} brace bug truncated caption capture to the bare label "
                "fragment: the 6 unwrapping-photonic-reservoirs figures and 4 "
                "minimal-quantum-reservoirs figures (delay-performance, delayANMSE, non-autonomous, "
                "timeseries) the fleet's ledger named, PLUS 4 mean-force-hamiltonians-from-influence-"
                "functionals figures (microscopic, strong_coupling, temp_dep, variance_scaling) the "
                "ledger UNDER-COUNTED — caught by the mechanical label-fragment detector (14 rows "
                "total). Their embed_text, caption_len, caption_size AND embeddings are built on the "
                "label fragment, not the real caption — flagged defective:caption-truncated-"
                "mechanical and excluded from the gate."),
            "dead_commented_source": (
                "four rows were extracted from %-commented-out or duplicate-label figure blocks not "
                "live in the compiled paper (FC-lra-errorsnodephasing, FC-qdei-convergence, "
                "FC-qdei-FH_rel_err, FC-mqrwhe-delays_example) — flagged defective:"
                "dead-commented-source and excluded."),
            "figure_under_capture": (
                "sequential-optical-response-suppression-for-chemical captures only 5 of its 8 "
                "figures (the atomiser missed 3 float blocks) — its figure inventory is incomplete."),
        },
    ),
}


def validate_residue_four_lens(store_name: str, paper_id: str, spec: StoreSpec,
                               skeleton: list[dict[str, Any]], residue: list[dict[str, Any]]) -> None:
    """Refuse ``paper_id``'s merge on ANY drift between residue and skeleton, for the four mechanical-
    view stores. The reader was handed the skeleton row and told to fill ONLY ``spec.residue_form_
    fields`` (+ stamp ``provenance.residue_read``); EVERYTHING ELSE — ``row_id``, ``embed_text``,
    every other ``form`` key, the whole ``provenance.span_ref`` — must return byte-identical. A reader
    that mutated any load-bearing invariant is not trusted to have read faithfully: raises
    :class:`ResidueDriftError` naming paper + row + field, and (like the paragraph precedent) the
    whole paper's merge is refused with nothing written."""
    sk = {r["row_id"]: r for r in skeleton}
    res = {r["row_id"]: r for r in residue}
    if set(sk) != set(res):
        diff = sorted(set(sk) ^ set(res))
        raise ResidueDriftError(
            f"{store_name}/{paper_id}: residue/skeleton row_id sets differ "
            f"(symmetric diff: {diff[:8]}{'...' if len(diff) > 8 else ''}) — merge refused")
    allowed_form = set(spec.residue_form_fields)
    for rid in sk:
        a, b = sk[rid], res[rid]
        if a["embed_text"] != b["embed_text"]:
            raise ResidueDriftError(
                f"{store_name}/{paper_id}/{rid}: embed_text drifted — merge refused")
        af, bf = a.get("form") or {}, b.get("form") or {}
        for k in set(af) | set(bf):
            if k in allowed_form:
                continue                                   # the reader was allowed to fill/replace k
            if af.get(k) != bf.get(k):
                raise ResidueDriftError(
                    f"{store_name}/{paper_id}/{rid}: form.{k} drifted "
                    f"({af.get(k)!r} != {bf.get(k)!r}) — a reader may only fill "
                    f"{sorted(allowed_form)}; merge refused")
        ap, bp = a.get("provenance") or {}, b.get("provenance") or {}
        # provenance must match on every skeleton key; the residue may ADD only `residue_read`.
        for k in ap:
            if ap.get(k) != bp.get(k):
                raise ResidueDriftError(
                    f"{store_name}/{paper_id}/{rid}: provenance.{k} drifted — merge refused")
        extra = set(bp) - set(ap)
        if extra - {"residue_read"}:
            raise ResidueDriftError(
                f"{store_name}/{paper_id}/{rid}: residue added provenance keys "
                f"{sorted(extra - {'residue_read'})} beyond residue_read — merge refused")


def enrich_row_four_lens(spec: StoreSpec, skeleton_row: dict[str, Any],
                         residue_row: dict[str, Any]) -> dict[str, Any]:
    """Build ONE enriched canonical row for a four-lens store: the SKELETON is authoritative on every
    invariant; the residue's ``spec.residue_form_fields`` are folded in; the overridden mechanical
    proxies are preserved (``spec.preserve_mechanical``, the audit trail — e.g. ``ladder_move_
    mechanical``); the coarse ``normalized_*`` class is derived when the store has a taxonomy;
    ``provenance.residue_read`` is carried through; the ledger's defective/caveat marks are stamped.
    Pure — mutates nothing the caller holds."""
    sk_form = json.loads(json.dumps(skeleton_row.get("form") or {}))   # deep copy (authoritative)
    res_form = residue_row.get("form") or {}
    form = dict(sk_form)
    for f in spec.residue_form_fields:                     # fold ONLY the reader-filled fields
        form[f] = res_form.get(f)
    for src, dst in spec.preserve_mechanical.items():      # preserve the overridden proxy for audit
        form[dst] = sk_form.get(src)
    if spec.taxonomy is not None:                          # derive the coarse gate class
        t = spec.taxonomy
        form[t.normalized] = _normalize_slug(form.get(t.fine), t.slug_to_class, t.fine)

    prov = json.loads(json.dumps(skeleton_row.get("provenance") or {}))  # deep copy (authoritative)
    res_read = (residue_row.get("provenance") or {}).get("residue_read")
    if res_read is not None:
        prov["residue_read"] = res_read

    enriched: dict[str, Any] = {
        "row_id": skeleton_row["row_id"],
        "embed_text": skeleton_row["embed_text"],         # his real span, skeleton-authoritative
        "form": form,
        "provenance": prov,
    }
    rid = skeleton_row["row_id"]
    # DEFECTIVE (findings a + b): the named ledger list wins (authoritative reason); a mechanical
    # detector then catches corrupted rows the ledger missed. Either way the row is EXCLUDED.
    reason = spec.defective_rows.get(rid)
    if reason is None and spec.defective_detector is not None:
        reason = spec.defective_detector(enriched)
    if reason is not None:
        enriched["defective"] = reason
    if rid in spec.caveat_rows:
        enriched["caveat"] = spec.caveat_rows[rid]        # findings (c) + (d): KEPT, flagged
    return enriched


def merge_residue(store_name: str, paper_id: str, *,
                  stores_root: Path | str | None = None,
                  consume_residue: bool = True) -> dict[str, Any]:
    """Fold ``<paper_id>.residue.jsonl`` into ``<paper_id>.jsonl`` as the enriched CANONICAL store
    file, validating EVERY residue row against its skeleton first (any drift raises
    :class:`ResidueDriftError` and nothing is written). ONE driver over all five stores: the
    paragraph_plan precedent keeps its bespoke offset-basis / length-band enrichment; the four
    mechanical-view stores dispatch on their :class:`StoreSpec` in :data:`FOUR_LENS_SPECS` (the
    validate + enrich differ by DATA; the load / write / consume / summary spine is shared). The
    canonical JSONL is written through ``stage_store.write_store``'s namespacing so the per-paper
    isolation law is reused, not re-implemented. On success the ``.residue.jsonl`` is CONSUMED —
    ``consume_residue=False`` keeps it (the hermetic tests do).

    Returns a summary: ``{paper_id, status, rows, defective, caveat, class_null, ...}``.
    """
    root = Path(stores_root) if stores_root is not None else CORPUS_STORES
    store_dir = root / store_name
    skeleton_path = store_dir / f"{paper_id}.jsonl"
    residue_path = store_dir / f"{paper_id}.residue.jsonl"
    if not skeleton_path.is_file():
        raise FileNotFoundError(f"merge_residue: no skeleton at {skeleton_path}")
    if not residue_path.is_file():
        raise FileNotFoundError(f"merge_residue: no residue at {residue_path}")

    skeleton = _load_jsonl(skeleton_path)
    residue = _load_jsonl(residue_path)
    res_by_id = {r["row_id"]: r for r in residue}

    spec = FOUR_LENS_SPECS.get(store_name)
    if spec is not None:
        validate_residue_four_lens(store_name, paper_id, spec, skeleton, residue)  # REFUSES on drift
        enriched = [enrich_row_four_lens(spec, sk, res_by_id[sk["row_id"]]) for sk in skeleton]
    else:                                                  # paragraph_plan — the precedent
        validate_residue_against_skeleton(paper_id, skeleton, residue)             # REFUSES on drift
        enriched = [enrich_row(sk, res_by_id[sk["row_id"]]) for sk in skeleton]

    # write the enriched rows AS the canonical <paper_id>.jsonl through the namespaced writer
    # (rebuilds a base _index.json; finalize_index re-writes it with the caveats block after).
    stage_store.write_store(store_name, paper_id, enriched, stores_root=root)

    if consume_residue:
        residue_path.unlink()

    n_defect = sum(1 for r in enriched if r.get("defective"))
    n_caveat = sum(1 for r in enriched if r.get("caveat"))
    summary: dict[str, Any] = {
        "paper_id": paper_id, "status": "validated", "rows": len(enriched),
        "defective": n_defect, "caveat": n_caveat,
    }
    if spec is not None:
        ck = spec.gate_class_key
        summary["class_null"] = sum(1 for r in enriched if r["form"].get(ck) is None)
    else:                                                  # paragraph_plan legacy keys (tests read them)
        n_norm = sum(1 for r in enriched if r["form"]["normalized_role"] is not None)
        summary["roles_normalized"] = n_norm
        summary["roles_null"] = len(enriched) - n_norm
        summary["class_null"] = len(enriched) - n_norm
    return summary


# --------------------------------------------------------------------------- #
# the store-level index with the caveats block (findings a + b) + defective rows
# --------------------------------------------------------------------------- #
#: The store-level caveats the readers PROVED (design's caveats block). Findings (a) + (b), one
#: sentence each — the provenance a downstream reader MUST know before trusting a row's offsets or
#: its connective adjacency.
STORE_CAVEATS = {
    "offset_basis": (
        "span_ref.char_start/char_end index the STRIPPED text produced by "
        "voice_corpus_ingest.strip_latex(), not a raw byte offset into the .tex file named in "
        "span_ref.file — three independent readers reproduced the ingest pipeline and matched the "
        "spans byte-for-byte (see span_ref.offset_basis on every row)."
    ),
    "connective_adjacency": (
        "The inherited chunker's paragraph boundaries are stripping artifacts in equation-dense "
        "passages — display-equation blocks eject as filtered-out chunks and some real paragraphs "
        "are split into fragments or dropped — so form.connective_prev/connective_next describe "
        "STORE-ROW adjacency, not always the paper's true rhetorical flow."
    ),
}


def _index_row(r: dict[str, Any]) -> dict[str, Any]:
    """A row's ``_index.json`` metadata — everything EXCEPT ``embed_text`` (no his-prose in the
    index), carrying the ``defective`` AND ``caveat`` markers forward so consumers can filter from
    the index alone (a defective row is never retrieved; a caveat row is retrieved but flagged)."""
    row = {"row_id": r["row_id"], "form": r["form"], "provenance": r["provenance"]}
    if r.get("defective"):
        row["defective"] = r["defective"]
    if r.get("caveat"):
        row["caveat"] = r["caveat"]
    return row


def finalize_index(store_name: str, *, stores_root: Path | str | None = None,
                   caveats: dict[str, str] | None = None) -> Path:
    """Rebuild the store-wide ``_index.json`` from every ``<paper_id>.jsonl`` present, adding the
    store-level ``caveats`` block (the fleet's §(e) findings), the ``defective_rows`` + ``caveat_
    rows`` lists, the ``gate_class`` name, and the taxonomy summary. This is the orchestrator-only
    fan-in, run ONCE after all papers are merged. One function over all five stores: the store-level
    caveats and taxonomy summary come from :data:`FOUR_LENS_SPECS` for the four mechanical-view
    stores, from the paragraph defaults (:data:`STORE_CAVEATS` + role taxonomy) otherwise."""
    root = Path(stores_root) if stores_root is not None else CORPUS_STORES
    store_dir = root / store_name
    spec = FOUR_LENS_SPECS.get(store_name)
    if caveats is None:
        caveats = spec.store_caveats if spec is not None else STORE_CAVEATS

    papers: list[dict[str, Any]] = []
    index_rows: list[dict[str, Any]] = []
    defective_rows: list[dict[str, Any]] = []
    caveat_rows: list[dict[str, Any]] = []
    for jf in sorted(store_dir.glob("*.jsonl")):
        prows = _load_jsonl(jf)
        papers.append({"paper_id": jf.stem, "rows": len(prows), "path": jf.name})
        for r in prows:
            index_rows.append(_index_row(r))
            if r.get("defective"):
                defective_rows.append({"row_id": r["row_id"], "paper_id": jf.stem,
                                       "reason": r["defective"]})
            if r.get("caveat"):
                caveat_rows.append({"row_id": r["row_id"], "paper_id": jf.stem,
                                    "reason": r["caveat"]})
    index: dict[str, Any] = {
        "schema": "stage-store/0.2",
        "store": store_name,
        "gate_class": spec.gate_class_key if spec is not None else "normalized_role",
        "caveats": caveats,
        "defective_rows": defective_rows,
        "caveat_rows": caveat_rows,
        "papers": sorted(papers, key=lambda p: p["paper_id"]),
        "row_count": len(index_rows),
        "rows": index_rows,
    }
    if spec is not None and spec.taxonomy is not None:                 # section_architecture
        t = spec.taxonomy
        index[t.index_key] = {"classes": t.classes, "n_slugs": len(t.slug_to_class), "file": t.file}
    elif spec is None:                                                 # paragraph_plan
        index["role_taxonomy"] = {"classes": ROLE_CLASSES, "n_slugs": len(SLUG_TO_CLASS),
                                  "file": "_role_taxonomy.json"}
    out = store_dir / "_index.json"
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


# --------------------------------------------------------------------------- #
# THE HOLDOUT GATE — nearest-exemplar-by-cosine class vote (the demo discipline)
# --------------------------------------------------------------------------- #
#: Signal-free draws for the ``identity`` baseline (the demo's ``BASELINE_DRAWS``); more draws =
#: steadier class-size-bias estimate. Deterministic (seeded per held-out item).
IDENTITY_BASELINE_DRAWS = 64


def nearest_exemplar_gate(
    rows: list[dict[str, Any]], embeddings: dict[str, list[float]], *,
    class_key: str = "normalized_role", shuffle: bool = False,
    holdout_fraction: float = 0.3, seed: int = 7,
    baseline: str = "identity",
) -> dict[str, Any]:
    """Gate the enriched store on held-out data (design §5): does his-prose cosine retrieval surface
    the right ``normalized_role`` class for a held-out row, beating the baseline? The picker is the
    demo's discipline VERBATIM — ``pick_fn(i)`` ranks each candidate class by its NEAREST OTHER row's
    cosine (leave-one-out). ``shuffle=True`` builds the PLANTED-BAD store (embeddings permuted,
    decoupled from classes) that must REFUSE. The rows passed in are already the gate-eligible set
    (defective + null-class rows excluded by the caller).

    ``baseline`` chooses the control:
      * ``"identity"`` (default, the demo's discipline + design §5's "identity baseline"): the SAME
        nearest-class ranking driven by a signal-free RANDOM query, averaged over
        :data:`IDENTITY_BASELINE_DRAWS` draws — so class-size bias is captured IDENTICALLY on both
        sides and only real query-signal moves ``score`` above it. This is the control that makes a
        signal-free store (the planted-bad) collapse onto the baseline and refuse.
      * ``"default"`` (``holdout_gate``'s ``baseline_fn=None``): the surfaced candidates scored with
        seeded-random floats. Generic, but it does NOT model class-size bias, so on a skewed-class
        store it under-baselines (~0.5) and a class-frequency-only picker beats it — it cannot serve
        as the refusal control here (surfaced in the verdict as the declared gap).
    """
    import numpy as np
    from laplace.pipeline.holdout_gate import holdout_gate

    classes = [r["form"][class_key] for r in rows]
    X = np.asarray([embeddings[r["row_id"]] for r in rows], dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    if shuffle:
        perm = np.random.default_rng(1_000_003).permutation(len(rows))
        X = X[perm]
    items = list(range(len(rows)))
    dim = X.shape[1] if len(rows) else 0

    def nearest_class_map(qv: "np.ndarray", i: int) -> dict[str, float]:
        sims = X @ qv
        best: dict[str, float] = {}
        for j in items:
            if j == i:
                continue
            c = classes[j]
            if sims[j] > best.get(c, -2.0):
                best[c] = float(sims[j])
        return best

    def pick_fn(i: int) -> dict[str, float]:
        return nearest_class_map(X[i], i)

    def truth_fn(i: int) -> str:
        return classes[i]

    def identity_baseline_fn(i: int) -> dict[str, float]:
        rng = np.random.default_rng([20260715, i])       # seeded per item -> replayable verdict
        acc: dict[str, list[float]] = {}
        for _ in range(IDENTITY_BASELINE_DRAWS):
            q = rng.standard_normal(dim)
            q /= max(float(np.linalg.norm(q)), 1e-12)
            for c, s in nearest_class_map(q, i).items():
                acc.setdefault(c, []).append(s)
        return {c: float(np.mean(v)) for c, v in acc.items()}

    baseline_fn = identity_baseline_fn if baseline == "identity" else None
    return holdout_gate(items, pick_fn=pick_fn, truth_fn=truth_fn, baseline_fn=baseline_fn,
                        holdout_fraction=holdout_fraction, seed=seed)
