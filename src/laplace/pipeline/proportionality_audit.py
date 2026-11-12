"""C9 — the claim/evidence proportionality gate (checklist cat 10).

Flag claim-strength vs evidence-strength mismatch where it is *mechanically*
detectable; the rest — the referee's judgement of whether the evidence earns the
claim — is R2's in Phase E. The two detectable mismatches:

* finite-size described as asymptotic — an asymptotic word ("asymptotic",
  "in the limit", "for all n", "scales as … law") in a sentence that also names
  finite-size evidence ("n ≤ 12", "tested range", "proof-of-principle",
  "observed"),
* fit presented as prediction — a prediction/law word ("predict", "law",
  "guarantee") applied to something the same sentence calls a fit/guide
  ("fitted", "guide", "consistent with", "empirical").

Both are emitted as ``proportionality``. The SSG abstract self-types plainly
("finite-size observations", "a guide … rather than an established law", "neither
asymptotic hardness nor quantum advantage"), so the gate must NOT flag those
hedged sentences — it fires only where the two strengths collide in one claim.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Union

from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline.apparatus_common import (
    finding, iter_paragraphs, iter_sentences, section_of, section_spans, summarise,
)
from laplace.pipeline.schema import (
    contribution_rank_id, is_pool_id, plan_sections, section_nodes,
    unwrap_contribution_rank,
)

_ASYMPTOTIC = re.compile(
    r"\b(asymptotic(?:ally)?|in the (?:thermodynamic )?limit|as\s+n\s*(?:→|\\to|\\rightarrow)|"
    r"for all\s+n|established law|proven scaling|in general)\b", re.I)
_FINITE = re.compile(
    r"(n\s*(?:≤|<=|\\le|\\leq)\s*\d+|\bfinite[- ]size\b|\btested range\b|\bproof[- ]of[- ]principle\b|"
    r"\bobserved\b|\bat (?:the )?sizes?\b|\bup to\s+n\b|\bsmall\b sizes)", re.I)
_PREDICTION = re.compile(r"\b(predict[s]?|prediction|guarantee[s]?|is a law|scaling law|establishes?|proves?)\b", re.I)
_FIT = re.compile(r"\b(fit(?:ted)?|guide[s]?|consistent with|empirical(?:ly)?|drawn alongside|not (?:fitted|asserted))\b", re.I)

# Explicit hedges: if the sentence disclaims the strong reading, it is truthful.
_HEDGE = re.compile(
    r"\b(neither|nor|not (?:a|an|assert|claim)|rather than|no (?:hardness|no-go|advantage)|"
    r"open (?:question|problem)|is no\b|does not\b|without (?:claiming|asserting)|"
    r"not (?:fitted|asserted|certified|established|a law))\b", re.I)


def check_proportionality(target: Union[str, Path]) -> dict[str, Any]:
    """Audit claim/evidence proportionality on a compiled manuscript."""
    target = Path(target)
    full = _gather_manuscript_text(target)
    spans = section_spans(full)

    findings: list[dict[str, Any]] = []
    for p_start, _p_end, para in iter_paragraphs(full):
        if re.match(r"\s*\\(begin|includegraphics|input)\b", para):
            continue
        for off, sent in iter_sentences(para):
            if _HEDGE.search(sent):
                continue                      # the sentence disclaims the strong reading
            pos = p_start + off
            slug, _t, _a = section_of(pos, spans)

            if _ASYMPTOTIC.search(sent) and _FINITE.search(sent):
                findings.append(finding(
                    f"{slug or '?'}",
                    "finite-size evidence described in asymptotic terms in one claim",
                    "state the claim at the evidence class it earns (a finite-size observation, not a scaling law)",
                    "proportionality", quote=sent.strip()))
            elif _PREDICTION.search(sent) and _FIT.search(sent):
                findings.append(finding(
                    f"{slug or '?'}",
                    "a fitted/guiding quantity is presented with prediction/law strength",
                    "call a guide a guide; reserve prediction/law for what the evidence certifies",
                    "proportionality", quote=sent.strip()))

    return {
        "pass": not findings,
        "findings": findings,
        "counts": summarise(findings),
    }


# ---------------------------------------------------------------------------
# C3.2 — the PRE-RENDER proportionality gate (keyed on meta.contribution_rank)
#
# The post-render gate above catches claim/evidence mismatch in the finished
# prose. This one runs on the PLAN, before a word is written: does the
# manuscript's MASS actually follow the author's ranking of contributions? The
# mass proxy is the pipeline's own — the planned-node count of a section (the
# same nodes_in_order + beats the plan validator sums into ``planned_node_count``)
# — attributed to a contribution through the C3.1 ``serves`` edge. A contribution
# is addressable in ``serves`` by its STABLE content-id (``contribution_rank_id``)
# or by its rank number (int or str), exactly as the validator resolves it.
#
# Three disproportions are flagged, all WARN-tier (the gate reports; the crank
# consumes the flags — it does not yet block a build):
#   * rank-1 does not hold the plurality of served mass,
#   * an EXCLUDED/exploratory contribution carries nonzero served mass,
#   * a lower rank outweighs a higher rank (a served-mass inversion).
# When NO section declares a resolvable ``serves`` the coverage is UNMEASURABLE
# and the gate says so — never a silent false pass.
# ---------------------------------------------------------------------------


def _section_mass(section: dict[str, Any]) -> int:
    """A section's planned-node mass — the proxy the plan validator already sums
    (``nodes_in_order``/``nodes`` + ``beats``). Figures/refs are support, not
    content mass (``schema.NON_CONTENT_PREFIXES`` idiom), so they are excluded.

    The exclusion is ENFORCED through ``schema.is_pool_id`` — the module's own
    named content-id predicate — and not merely asserted in prose. It was
    asserted here and not applied, and APPENDICES really do carry ``fig:`` ids in
    ``nodes_in_order`` (``validate_projection_plan.validate`` checks provenance on
    exactly that shape), so support ids inflated served mass. An appendix of three
    ``fig:``/``ref:`` ids beside one content node weighed 4 against a body section's
    2 and manufactured a rank INVERSION out of apparatus — a FALSE FLAG, which
    spends the gate's credibility just as surely as a false pass. ``is_pool_id``
    also drops the ``<section>-p<N>`` paragraph spec ids (prose provenance, never
    nodes)."""
    ids = section_nodes(section) + list(section.get("beats") or [])
    return sum(1 for x in ids if isinstance(x, str) and is_pool_id(x))


def _rank_keys(n: Any) -> list[Any]:
    """The rank-NUMBER index keys an authored ``rank`` field contributes —
    ``[n, str(n)]`` for a real number, ``[]`` for anything else. The deliberate
    mirror of ``validate_projection_plan._rank_keys``: that module is a *script*
    loaded by file path (``storyboard._validate_reduced``, ``verify.py:990``), so
    the library cannot import from it — the two doors are kept identical by this
    note rather than by an import.

    Fail-closed against a MALFORMED authored rank, which reaches here whenever the
    plan is shape-defective (``check_contribution_rank`` REPORTS that defect, it
    does not gate this call): ``{"rank": [], …}`` is unhashable and indexing on it
    raised ``TypeError`` *inside* ``check_plan_proportionality``. That is not a
    loud failure — ``storyboard._validate_reduced`` converts a raised validator
    into ``{"pass": True}``, so the crash laundered the WHOLE pre-render plan
    validation into a silent green. Here the entry simply loses its rank-number
    door and keeps its content-id one (the id is IDENTITY, the rank is a POSITION).

    ``bool`` is excluded FIRST: ``True == 1`` and ``hash(True) == hash(1)``, so a
    ``{"rank": true}`` entry would otherwise seize the rank-1 key and swallow a
    legitimate ``serves: 1`` — measured before the cure, the decoy took the mass
    and the real rank-1 was credited 0."""
    if isinstance(n, bool) or not isinstance(n, (int, str)):
        return []
    return [n, str(n)]


def _rank_sort_key(c: dict[str, Any]) -> tuple[int, float, str]:
    """A TOTAL order over authored ranks that never compares an ``int`` to a
    ``str``. ``sorted(primaries, key=lambda c: c["rank"])`` and the matching
    ``min(...)`` raised ``TypeError`` on a plan mixing ``{"rank": 1}`` with
    ``{"rank": "2"}`` — the same crash-laundered-into-a-pass path as
    ``_rank_keys`` guards. Real numbers order numerically and FIRST; every other
    shape sorts after them, deterministically, by its string form. The shape
    itself is already reported by ``check_contribution_rank``; this only ensures
    the audit still delivers its report instead of dying before it."""
    n = c.get("rank")
    if not isinstance(n, bool) and isinstance(n, (int, float)):
        return (0, float(n), "")
    return (1, 0.0, str(n))


def _contributions(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse ``meta.contribution_rank`` into ordered contribution records
    ``{id, rank, claim, role, excluded}``. The one decode (mirrors the validator's
    ``contribution_index``/``_excluded_index`` split): a role reading as
    excluded/exploratory demotes the claim. Empty for an absent/malformed rank —
    the additive floor (nothing to measure changes nothing). The respine
    ``{value, projection_ruling}`` envelope is unwrapped through the one shared
    reader so the mass audit weighs the ratified thesis, never the wrapper."""
    rank = unwrap_contribution_rank((meta or {}).get("contribution_rank"))
    out: list[dict[str, Any]] = []
    if not isinstance(rank, list):
        return out
    for i, item in enumerate(rank, 1):
        if isinstance(item, dict):
            claim = str(item.get("claim") or "").strip()
            role = str(item.get("role") or "").strip()
            n = item.get("rank", i)
        elif isinstance(item, str):
            claim, role, n = item.strip(), "", i
        else:
            continue
        if not claim:
            continue
        role_l = role.lower()
        excluded = "excluded" in role_l or "exploratory" in role_l
        out.append({"id": contribution_rank_id(claim), "rank": n,
                    "claim": claim, "role": role, "excluded": excluded})
    return out


def check_plan_proportionality(plan: dict[str, Any]) -> dict[str, Any]:
    """PRE-RENDER proportionality: measure per-contribution manuscript mass from
    the plan's ``serves`` edges and flag where mass does not follow the ranking.

    Returns the module's standard shape (``pass``/``findings``/``counts``) plus
    ``measurable`` (True/False, or None when there is no rank to measure) and a
    ``coverage`` table (contribution id → its rank/claim/role/mass/serving
    sections) the crank consumes. ``pass`` is plain: an unmeasurable plan does
    NOT pass silently."""
    meta = (plan or {}).get("meta") or {}
    contribs = _contributions(meta)
    findings: list[dict[str, Any]] = []

    if not contribs:
        # Nothing was ranked: there is genuinely nothing to weigh (the additive
        # floor). Not a defect, not a false pass — measurability is undefined.
        return {"pass": True, "findings": [], "counts": {},
                "measurable": None, "coverage": {}}

    # id -> contribution; ref (id | rank int | rank str) -> id, as C3.1 resolves.
    by_id = {c["id"]: c for c in contribs}
    ref_index: dict[Any, str] = {}
    for c in contribs:
        ref_index[c["id"]] = c["id"]
        for key in _rank_keys(c["rank"]):   # skipped for a malformed/bool rank
            ref_index[key] = c["id"]

    mass: dict[str, int] = {c["id"]: 0 for c in contribs}
    served_by: dict[str, list[str]] = {c["id"]: [] for c in contribs}
    serving_sections = 0
    for sec in plan_sections(plan):
        if not isinstance(sec, dict):
            continue          # a malformed `sections` entry (or a `sections: "str"`,
                              # which plan_sections yields CHARACTER by character)
                              # raised AttributeError on `.get` — again a crash the
                              # storyboard's caller laundered into `{"pass": True}`.
                              # An unreadable section attributes no mass; the shape
                              # defect is the plan validator's to report, and the
                              # audit still delivers its coverage table.
        raw = sec.get("serves")
        if raw is None:
            continue
        refs = raw if isinstance(raw, list) else [raw]
        refs = [r for r in refs if r is not None and r != ""]
        if not refs:
            continue
        m = _section_mass(sec)
        sid = sec.get("id", "?")
        resolved = False
        for ref in refs:
            if isinstance(ref, bool) or not isinstance(ref, (str, int)):
                continue                       # non-scalar ref (dict/list) — unresolvable,
                                               # like an unknown ref (the validator FAILS on it);
                                               # counted toward unmeasurable, never a crash.
                                               # bool excluded FIRST: hash(True)==hash(1), so a
                                               # bare `serves: true` would silently credit rank-1
            cid = ref_index.get(ref)
            if cid is None:
                continue                       # unknown ref — the validator FAILS on it
            mass[cid] += m
            served_by[cid].append(sid)
            resolved = True
        if resolved:
            serving_sections += 1

    coverage = {c["id"]: {"rank": c["rank"], "claim": c["claim"], "role": c["role"],
                          "excluded": c["excluded"], "mass": mass[c["id"]],
                          "sections": served_by[c["id"]]} for c in contribs}

    if serving_sections == 0:
        # No section attributes mass to any contribution: coverage cannot be
        # measured. Report it plainly (never a silent clean bill).
        findings.append(finding(
            "plan.meta.contribution_rank",
            "contribution coverage is UNMEASURABLE: no section declares a resolvable `serves`",
            "declare `serves` on sections so per-contribution manuscript mass can be weighed",
            "proportionality"))
        return {"pass": False, "findings": findings, "counts": summarise(findings),
                "measurable": False, "coverage": coverage}

    primaries = [c for c in contribs if not c["excluded"]]
    excluded = [c for c in contribs if c["excluded"]]

    # (1) an excluded/exploratory contribution the manuscript is nonetheless serving
    for c in excluded:
        if mass[c["id"]] > 0:
            findings.append(finding(
                c["claim"][:80],
                f"excluded contribution carries nonzero served mass "
                f"({mass[c['id']]} planned nodes across {len(served_by[c['id']])} section(s))",
                "an excluded/exploratory contribution should not be served by the "
                "manuscript body — drop its `serves` or promote the contribution",
                "proportionality"))

    # (2) rank inversion — a lower rank outweighs a higher rank. One finding per
    # inverting contribution, naming the highest rank it overtakes.
    prim_by_rank = sorted(primaries, key=_rank_sort_key)
    for i, lo in enumerate(prim_by_rank):
        for hi in prim_by_rank[:i]:            # strictly higher rank (lower number)
            if mass[lo["id"]] > mass[hi["id"]]:
                findings.append(finding(
                    lo["claim"][:80],
                    f"rank {lo['rank']} carries more served mass ({mass[lo['id']]}) than "
                    f"the higher rank {hi['rank']} ({mass[hi['id']]}) — a proportionality inversion",
                    "rebalance section coverage so served mass follows the contribution ranking",
                    "proportionality"))
                break

    # (3) rank-1 does not hold the plurality of served mass (tie counts as failure
    # — a plurality is THE largest share). Only meaningful once some mass exists.
    if primaries and any(mass[c["id"]] > 0 for c in primaries):
        top = min(primaries, key=_rank_sort_key)
        others = [c for c in primaries if c["id"] != top["id"]]
        if any(mass[c["id"]] >= mass[top["id"]] for c in others):
            findings.append(finding(
                top["claim"][:80],
                f"rank-1 does not hold the plurality of served mass "
                f"(rank-1 mass {mass[top['id']]}; a lower rank matches or exceeds it)",
                "the rank-1 contribution should carry the largest share of manuscript mass",
                "proportionality"))

    return {"pass": not findings, "findings": findings, "counts": summarise(findings),
            "measurable": True, "coverage": coverage}
