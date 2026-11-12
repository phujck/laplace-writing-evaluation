"""R10 Restart — the whole-artefact judgement grade (the return path's missing organ).

The altitude directive's law made an organ: *a lower-grade judge must never certify a
higher-grade property.* Every reader before R10 reads a SLICE (R1 the whole flattened
``.tex``, R5/R6/R9 crops, R7 the prose, R2 the claims) — and every one of them reads
the BLUEPRINT (``graph._gather_manuscript_text``, the flattened ``.tex``), never the
finished object. R10 is the higher grade, built at last: a blind reader of the COMPLETE
RENDERED PDF, GIVEN the intended object, empowered to RESPINE / RESTART.

**Two phases, the seal INVERTED between them.**

  * **Phase 1 — BLIND.** The reader meets the whole *rendered PDF text* (extracted
    from the finished PDF, not the ``.tex`` — reading the blueprint is exactly what
    the whole-artefact grade forbids) and a RECOVERY QUESTIONNAIRE: what paper did you
    meet — the primary contribution, the evidence bearing its weight, the rhetorical
    weighting by section, what the conclusion claims was achieved, what seems
    deliberately excluded. NO plan, NO meta, NO ``.tex``. This packet passes
    ``sealed.seal_holds`` — the TOTAL seal must hold.

  * **Phase 2 — COMPARE.** The blind recovery is set beside the INTENDED OBJECT
    (``meta.contribution_rank``, thesis-like meta keys, exclusions). This is the one
    moment the reader is handed the intention — comparing the blind recovery against
    intent IS its function — so the packet is DELIBERATELY seal-inverted:
    :func:`compare_seal_inverted` proves the intended object is *present* (its absence
    is the defect here), the mirror of a normal seal. The standard SPEC/INTENT scrub
    (``sealed.SPEC_SENTINELS`` / ``referee.INTENT_SENTINELS``) is NOT applied to this
    packet, and could not be — it would strip the very material the compare needs.
    **Exemption placement:** seal scrubs are per-reader — each pack function calls its
    own check, and ``referee.INTENT_SENTINELS`` runs ONLY inside
    ``referee.pack_for_referee_read``. There is no central scrub over all readers, so
    R10 is exempt BY CONSTRUCTION: ``compare_packet`` simply never invokes it.

    The compare packet also takes an OPTIONAL **closed section-id vocabulary**
    (``sid_roster``, ``{sid: title}`` — ids and titles only, never jobs, never the
    plan), which constrains ``object_key`` to a real address plus an artefact-kind
    ESCAPE HATCH (:data:`ARTEFACT_OBJECT_KEY`). Resolution downstream is EXACT by law,
    so an unaddressed reader's invented keys ("weighting", "Section V") reach no
    actuator; the roster closes that at the source instead of loosening the match.
    ``sid_roster=None`` is byte-compatible with the packet before it existed.

**The verb law.** Every disagreement the compare names is a *mismatch* whose TYPE maps
— through :data:`MISMATCH_TABLE`, a documented table that is surjective onto
``adjudicate.PROJECTION_VERBS`` — to a plan-altitude verb and one of R10's owned
finding-kinds. :func:`bank` writes ONE ``reader-report`` record and, per mismatch, a
DRAFT ``projection-intent`` (``adjudicate.make_projection_intent``, actor
``R10:restart-reader``, draft-only law). Consequences flow through those draft intents,
never per-node work — which is why R10's finding-kinds are VERDICT-ONLY in the schema.

Following the reader-suite pattern (sealed.py / caption_blind.py): this module PACKAGES
the two reads and BANKS the verdict — it does NOT call a model. The orchestrator drives
the two sealed phases at candidate-lock with :func:`blind_packet` / :func:`compare_packet`
and hands the parsed replies to :func:`bank`.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline.readers.roster import READERS, reader_finding
from laplace.pipeline.readers.sealed import seal_holds

_RID = "R10"
_ACTOR = "R10:restart-reader"
_EXTRACT_TIMEOUT = 300


# ---------------------------------------------------------------------------
# 1. The harness — whole-PDF text from the FINISHED object (never the blueprint)
# ---------------------------------------------------------------------------
#
# Extracted in an ephemeral ``uv run --with pypdfium2`` subprocess (the visual_gate
# idiom), so the main venv needs no pypdfium2. ``TextPage.get_text_range()`` dumps a
# whole page's text; poppler ``pdftotext - `` is the fallback when uv/pypdfium2 is
# absent. If neither works the failure is LOUD and names BOTH (silence never reads as
# pass): a whole-artefact judge with no artefact text must not quietly certify.

_EXTRACT_SCRIPT = r'''
import sys
import pypdfium2 as pdfium
doc = pdfium.PdfDocument(sys.argv[1])
parts = []
for i in range(len(doc)):
    tp = doc[i].get_textpage()
    try:
        t = tp.get_text_range()
    except Exception:
        t = tp.get_text_bounded()
    parts.append(t)
sys.stdout.write("\n\n".join(parts))
'''


def _resolve_uv() -> Optional[str]:
    """The uv binary, in the directive's precedence: ``LAPLACE_UV_BIN`` env →
    ``shutil.which('uv')`` → ``visual_gate.DEFAULT_UV`` (this box's default and his
    Windows box's, honoured last). Returns the first candidate that resolves to a real
    executable/file, else ``None``."""
    from laplace.pipeline import visual_gate
    for cand in (os.environ.get("LAPLACE_UV_BIN"), shutil.which("uv"),
                 visual_gate.DEFAULT_UV):
        if not cand:
            continue
        if shutil.which(cand) or Path(cand).is_file():
            return cand
    return None


def _extract_via_uv(pdf_path: Path, uv_bin: str, timeout: int) -> str:
    """Whole-document text via the isolated pypdfium2 subprocess. Raises on a nonzero
    subprocess (a broken extractor is a loud signal, never a silent empty read)."""
    proc = subprocess.run(
        [uv_bin, "run", "--no-project", "--with", "pypdfium2", "python", "-c", _EXTRACT_SCRIPT,
         str(pdf_path)],
        capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pypdfium2 extract failed (rc={proc.returncode}): "
                           f"{(proc.stderr or proc.stdout)[-400:]}")
    return proc.stdout or ""


def _extract_via_poppler(pdf_path: Path, timeout: int) -> Optional[str]:
    """Whole-document text via poppler ``pdftotext <pdf> -`` (stdout), the fallback
    when uv/pypdfium2 is unavailable. Returns ``None`` when no poppler build is present
    or the run fails — the caller then names both extractors in one plain error."""
    from laplace.manuscript.projection_viewer import _poppler_pdftotext
    exe = _poppler_pdftotext()
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, str(pdf_path), "-"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout or ""


def artefact_pdf_binding(manuscript_dir: Union[str, Path], *,
                         plan: Any = None) -> dict[str, Any]:
    """WHICH PDF this reader will meet, and why — ``release.artefact_pdf_binding``
    (``{pdf, source, target_dir, plan_path, refused, reason}``). Exposed so a run can
    PRINT the object it bound instead of discovering three months later that the
    whole-artefact grade was reading a figure-review audit."""
    from laplace.pipeline import release
    return release.artefact_pdf_binding(manuscript_dir, plan=plan)


def extract_artefact_text(manuscript_dir: Union[str, Path], *,
                          plan: Any = None,
                          uv_bin: Optional[str] = None,
                          timeout: int = _EXTRACT_TIMEOUT) -> str:
    """The whole rendered-PDF text of the FINISHED artefact. The PDF is bound through
    ``release.artefact_pdf_binding`` — the PROJECT's finished object, not merely the
    manuscript dir's: when the plan declares ``meta.target_dir`` the artefact resolves
    THERE (its finalize record → the slug PDF → ``main.pdf`` → the newest ``release/``
    deposit) and the manuscript dir's top-level PDF is NOT a fall-through; with no
    target dir declared it is the shared ``release._discover_final_pdf`` ladder, except
    that an audit-named PDF (FIGURE_REVIEW, judge_rounds, calibration) may never bind
    on the guessed rung. ``plan`` may be a dict or a path; ``None`` reads the committed
    ``<manuscript>/projection_plan.json`` when it exists — the same file the compare
    phase opens, so the two phases can never disagree about which project they are in.

    Text is pulled by the isolated pypdfium2 subprocess (uv resolution:
    ``LAPLACE_UV_BIN`` → ``which('uv')`` → ``visual_gate.DEFAULT_UV``), with poppler
    ``pdftotext`` as the fallback. If no extractor works the error names BOTH — a
    whole-artefact judge with no artefact text must fail loudly, never certify on
    silence."""
    mdir = Path(manuscript_dir)
    binding = artefact_pdf_binding(mdir, plan=plan)
    rel = binding.get("pdf")
    if not rel:
        raise RuntimeError(
            f"restart_reader: no final PDF to bind under {mdir} "
            f"({binding.get('reason') or 'release.artefact_pdf_binding found none'} "
            "— finalize first)")
    pdf_path = (mdir / rel).resolve()
    if not pdf_path.is_file():
        raise RuntimeError(
            f"restart_reader: bound PDF {rel!r} is missing at {pdf_path}")

    errors: list[str] = []
    uv = uv_bin or _resolve_uv()
    if uv:
        try:
            txt = _extract_via_uv(pdf_path, uv, timeout)
            if txt.strip():
                return txt
            errors.append(f"pypdfium2 via {uv!r} returned empty text")
        except Exception as e:                       # loud, then fall through to poppler
            errors.append(f"pypdfium2 via {uv!r}: {e}")
    else:
        errors.append("uv not resolvable "
                      "(LAPLACE_UV_BIN / which('uv') / visual_gate.DEFAULT_UV)")

    pop = _extract_via_poppler(pdf_path, timeout)
    if pop and pop.strip():
        return pop
    errors.append("poppler pdftotext unavailable or produced no text")

    raise RuntimeError(
        "restart_reader.extract_artefact_text: no working PDF text extractor for "
        f"{pdf_path} — " + "; ".join(errors))


# ---------------------------------------------------------------------------
# 2. Phase 1 — the BLIND packet (recovery questionnaire, TOTAL seal)
# ---------------------------------------------------------------------------

#: what paper did you meet — the recovery questionnaire. Deliberately worded to hold
#: NO construction sentinel (``sealed.SPEC_SENTINELS``), so the blind packet seals.
_RECOVERY_QUESTIONNAIRE: tuple[str, ...] = (
    "the PRIMARY CONTRIBUTION — the one thing this paper claims to add (one line)",
    "the EVIDENCE bearing its weight — what actually carries the primary claim",
    "the RHETORICAL WEIGHTING by section — which sections the paper spends itself on, "
    "most prominent first",
    "what the CONCLUSION claims was ACHIEVED",
    "what seems DELIBERATELY EXCLUDED — the questions the paper pointedly does not take up",
)

BLIND_INSTRUCTION = (
    "You are meeting a finished paper for the FIRST time, as its blindest reader: you "
    "have ONLY the rendered pages in front of you — no plan, no author's intention, no "
    "source, no summary of what it was meant to be. Read the whole artifact and RECOVER "
    "the paper you actually met. Do NOT orient on what you happen to know about the "
    "field, and do NOT guess at intention — report only what THESE PAGES deliver. For "
    "each item in the recovery questionnaire, state what you recovered and, where you "
    "can, quote where; where a page does not deliver an item, say so plainly."
)

_BLIND_SCHEMA_KEYS: tuple[str, ...] = (
    "contribution", "evidence", "weighting", "conclusion_claims", "excluded")


def blind_packet(text: str, *, max_input_chars: int = 200_000) -> dict[str, Any]:
    """The PHASE-1 (blind) packet: the artefact text + the recovery questionnaire and
    NOTHING else — no plan, no meta, no ``.tex``. Mirrors ``sealed.pack_for_sealed_read``:
    the input is capped (recorded in ``truncated`` so a truncated read is never mistaken
    for a full one — silence never reads as pass), and ``seal_check`` runs
    ``sealed.seal_holds`` over the built packet, which MUST hold (the blind reader is
    denied every construction sentinel)."""
    truncated = len(text) > max_input_chars
    sealed_input = text[:max_input_chars]
    checklist = "\n".join(f"  {i + 1}. {q}"
                          for i, q in enumerate(_RECOVERY_QUESTIONNAIRE))
    prompt = (
        f"{BLIND_INSTRUCTION}\n\n"
        f"RECOVERY QUESTIONNAIRE:\n{checklist}\n\n"
        'Return ONLY JSON: {"contribution": "<one line>", "evidence": "<what carries '
        'it>", "weighting": ["<section>: <how much weight>", ... most prominent first], '
        '"conclusion_claims": "<what the conclusion says was achieved>", "excluded": '
        '["<what the paper pointedly does not take up>", ...]}. Answer from the pages '
        "alone.\n\n"
        "=== THE ARTIFACT (read only this) ===\n"
        f"{sealed_input}"
    )
    payload: dict[str, Any] = {
        "reader": _RID,
        "organ": "sealed_subagent",
        "phase": "blind",
        "model_hint": "least-capable (worse is better — a narrower knowledge base is "
                      "the more faithful blind cold-reader proxy)",
        "instruction": BLIND_INSTRUCTION,
        "recovery_questionnaire": list(_RECOVERY_QUESTIONNAIRE),
        "recovery_schema": list(_BLIND_SCHEMA_KEYS),
        "seal": {"denies": list(READERS[_RID].seal_denies),
                 "allows": list(READERS[_RID].seal_allows),
                 "statement": READERS[_RID].seal},
        "sealed_input": sealed_input,
        "prompt": prompt,
        "truncated": truncated,
    }
    payload["seal_check"] = seal_holds(payload)      # PHASE-1 seal MUST hold
    return payload


# ---------------------------------------------------------------------------
# 3. Phase 2 — the COMPARE packet (the seal INVERSION, deliberate + documented)
# ---------------------------------------------------------------------------

COMPARE_INSTRUCTION = (
    "You now compare the paper you recovered BLIND against the INTENDED OBJECT — what "
    "this paper was meant to be. This is the ONE moment you are given the intention: "
    "comparing your blind recovery to it IS your function. Name every place the "
    "recovered paper and the intended object DISAGREE — the primary contribution, the "
    "rhetorical weighting, what the conclusion claims was achieved, and what was meant "
    "to be excluded. Do NOT soften a mismatch because you can imagine how it happened; "
    "the recovered paper is the paper that shipped."
)

#: The artefact-kind ESCAPE HATCH (W2-S1). The compare reader writes this literal as its
#: ``object_key`` when a disagreement belongs to NO id in the closed vocabulary and to no
#: meta key — the artefact as a whole, a section the plan never carried, a cross-cutting
#: weighting. It is deliberately un-sid-like and un-key-like so it can never collide with
#: a real target, and it resolves ``"unresolved"`` under
#: :func:`_resolve_findings_against_plan` like any other unaddressable key: the finding
#: BANKS (the mismatch stays expressible and reaches the author) and :func:`bank` mints NO
#: projection-intent. That is the whole point of the hatch — a mismatch about something
#: absent from the roster must stay SAYABLE rather than be forced onto a wrong sid, where
#: it would mint a real actuator pointed at an innocent section.
ARTEFACT_OBJECT_KEY = "__artefact__"


def _checked_sid_roster(sid_roster: Any, meta_keys: list[str]) -> dict[str, str]:
    """Validate + normalise the CLOSED section-id vocabulary — ``{sid: title}``, IDS AND
    TITLES ONLY. Fail-LOUD (the :func:`_mismatches_of` idiom): a roster that cannot
    constrain is worse than no roster at all, because the prompt would still announce a
    closed vocabulary the reader could not honour, and every mismatch it produced would
    look authoritative while naming nothing.

    Refused: a non-mapping; an EMPTY mapping (constrains nothing — pass ``None`` for the
    unconstrained packet); a blank or multi-line sid; a duplicate sid; a sid equal to
    :data:`ARTEFACT_OBJECT_KEY`; and a sid that COLLIDES with a meta key of the intended
    object — the two namespaces the compare's ``object_key`` may name must stay disjoint
    or the key is ambiguous (and the resolver namespaces by ``object_kind``, so an
    ambiguous key would silently resolve in only one of them).

    Titles are whitespace-collapsed to a single line: they exist to let the reader
    RECOGNISE the section it means, and they carry no unearned information — the titles
    are printed on the rendered pages the blind phase already read. Nothing else from the
    plan is admitted: no jobs, no node lists, no section contracts, no plan at all."""
    if not isinstance(sid_roster, dict):
        raise ValueError("restart_reader: sid_roster must be a {sid: title} mapping "
                         f"(got {type(sid_roster).__name__}); pass None for no roster")
    if not sid_roster:
        raise ValueError("restart_reader: sid_roster is EMPTY — an empty vocabulary "
                         "constrains nothing; pass None for the unconstrained packet")
    out: dict[str, str] = {}
    for sid, title in sid_roster.items():
        if not isinstance(sid, str) or not sid.strip() or "\n" in sid:
            raise ValueError(f"restart_reader: sid_roster key {sid!r} is not a "
                             "single-line, non-empty section id")
        key = sid.strip()
        if key in out:
            raise ValueError(f"restart_reader: sid_roster names {key!r} twice")
        if key == ARTEFACT_OBJECT_KEY:
            raise ValueError(f"restart_reader: sid_roster id {key!r} is the artefact "
                             "escape hatch — the hatch may never name a real section")
        if key in meta_keys:
            raise ValueError(
                f"restart_reader: sid_roster id {key!r} collides with a meta key of the "
                "intended object — the section and meta namespaces must stay disjoint "
                "or an object_key naming it is ambiguous")
        out[key] = " ".join(str("" if title is None else title).split())
    if ARTEFACT_OBJECT_KEY in meta_keys:
        raise ValueError(f"restart_reader: the intended object carries a meta key "
                         f"{ARTEFACT_OBJECT_KEY!r} — that is the artefact escape hatch "
                         "and may never name a real target")
    return out


#: The CLOSED vocabulary of EXCLUSION-CLASS roles in ``meta.contribution_rank``. A rank
#: entry whose ``role`` is one of these marks its claim as deliberately left out — which
#: is an exclusions statement, authored INSIDE the rank rather than beside it in a
#: separate ``meta.exclusions`` key. Both forms are legitimate authorings of the same
#: judgement (the live SSG plan carries only the role form: rank 4, the planted hardness
#: construction, role ``exploratory-excluded``), so :func:`compare_seal_inverted` accepts
#: either.
#:
#: Matching is FAIL-CLOSED: exact membership in this set after stripping surrounding
#: whitespace and case-folding, and NOTHING else — no substring, no prefix, no stem. A
#: role of ``"excluded-by-the-author"`` or ``"exploratory-but-kept"`` does NOT satisfy the
#: seal. That is deliberately STRICTER than ``schema.contribution_rank_lines``, which
#: demotes a claim to the excluded line on the substring test
#: (``"excluded" in role or "exploratory" in role``). The two may only diverge in the safe
#: direction — every role here MUST also read as excluded under that decode (asserted in
#: the tests), so the seal can refuse a rank the renderer would have shown as excluded,
#: but can never seal one the renderer would have shown as primary. A seal that guesses
#: is not a seal; an unrecognised role means the author says so in ``meta.exclusions``.
EXCLUSION_ROLES: frozenset[str] = frozenset({
    "excluded",
    "exploratory",
    "exploratory-excluded",
})


def rank_exclusion_roles(rank: Any) -> list[str]:
    """The exclusion-class roles actually carried by ``meta.contribution_rank`` — the
    role-form exclusions statement, in rank order, de-duplicated.

    The respine ``{value: ...}`` envelope is peeled by the ONE decode
    (``schema.unwrap_contribution_rank``), so a singly- or doubly-wrapped rank is read
    the same as a bare list; this module keeps no second copy of that shape logic. Only
    ``{rank, claim, role}`` dict entries can carry a role, so a plain list of claim
    strings yields ``[]``. An entry with no claim text is skipped — it is malformed and
    the renderer already drops it, so it may not carry a seal either. Any non-list shape
    yields ``[]`` (fail-closed: an unreadable rank states no exclusions)."""
    from laplace.pipeline import schema as _schema

    entries = _schema.unwrap_contribution_rank(rank)
    if not isinstance(entries, (list, tuple)):
        return []
    found: list[str] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        if not str(item.get("claim") or "").strip():
            continue
        role = str(item.get("role") or "").strip()
        if role.casefold() in EXCLUSION_ROLES and role not in found:
            found.append(role)
    return found


def compare_seal_inverted(payload: dict[str, Any]) -> dict[str, Any]:
    """The DELIBERATE seal inversion, proved. Phase 1 (:func:`blind_packet`) runs the
    standard ``sealed.seal_holds`` and MUST pass — the reader is denied the intention.
    Phase 2 INVERTS it: the intended object is handed over ON PURPOSE, because comparing
    the blind recovery against intent IS this reader's function. So the SPEC/INTENT
    sentinel scrub (``sealed.SPEC_SENTINELS`` / ``referee.INTENT_SENTINELS``) is NOT
    applied here — it would strip the very material the compare needs. This check is the
    INVERSE of a seal: it proves the intended object IS present (a compare packet with
    no intention is the real defect).
    ``{ok, inverted, intended_present, exclusions_form, exclusion_roles, note}`` — ``ok``
    is True iff the intended object carries ``contribution_rank`` AND an exclusions
    statement in either authored form. ``exclusions_form`` names which form carried it:
    ``"meta.exclusions"`` (the separate key), ``"contribution_rank.role"`` (an
    exclusion-class role inside the rank — see :data:`EXCLUSION_ROLES`), ``"both"``, or
    ``"none"`` when neither is present and the seal refuses.

    Placement: the seal scrub is per-reader (each pack calls its own check;
    ``referee.INTENT_SENTINELS`` runs ONLY inside ``referee.pack_for_referee_read``), so
    R10 is exempt BY CONSTRUCTION — there is no central scrub to carve an exception out
    of, and ``compare_packet`` simply never invokes it."""
    intended = payload.get("intended") or {}
    # The intended object must carry the HIERARCHY, not merely be non-empty: the
    # contribution rank (what the paper claims, ordered) AND an exclusions statement
    # (what it means to leave out). Without both there is nothing the compare can hold
    # the recovered paper against on the axes R10 owns, so a bare non-empty dict no
    # longer seals — the inverse defect this seal proves is 'the intention is missing'.
    #
    # The exclusions statement has TWO legitimate authorings and the seal reads BOTH
    # (his ruling PV-20260820T223004Z). The KEY form declares a separate
    # ``meta.exclusions`` carrier; the ROLE form authors the exclusion inside the rank
    # itself, as an entry whose role is exclusion-class (:data:`EXCLUSION_ROLES`) — the
    # form the live SSG plan actually uses, and the reason this seal had failed there
    # since it was written. Either satisfies the exclusions half; NEITHER still fails.
    # The role read is exact against a closed vocabulary, never a substring sniff: the
    # seal refuses what it does not recognise rather than guessing an intention.
    rank = intended.get("contribution_rank")
    has_rank = bool(rank)
    has_exclusions_key = "exclusions" in intended
    exclusion_roles = rank_exclusion_roles(rank)
    has_exclusions = has_exclusions_key or bool(exclusion_roles)
    present = has_rank and has_exclusions
    if has_exclusions_key and exclusion_roles:
        form = "both"
    elif has_exclusions_key:
        form = "meta.exclusions"
    elif exclusion_roles:
        form = "contribution_rank.role"
    else:
        form = "none"
    if present:
        carrier = ("meta.exclusions" if form == "meta.exclusions" else
                   f"contribution_rank role(s) {', '.join(exclusion_roles)}"
                   if form == "contribution_rank.role" else
                   "meta.exclusions + contribution_rank role(s) "
                   f"{', '.join(exclusion_roles)}")
        note = ("compare phase is seal-INVERTED: the intended object is present by "
                f"design (comparing against intent is R10's function); exclusions "
                f"carried by {carrier}")
    else:
        missing = ", ".join(name for name, ok in
                            (("contribution_rank", has_rank),
                             ("exclusions", has_exclusions)) if not ok)
        note = (f"compare packet's intended object is incomplete (missing: {missing}) "
                "— nothing to compare against on R10's axes; supply "
                "meta.contribution_rank plus EITHER a meta.exclusions key OR a rank "
                f"entry whose role is one of: {', '.join(sorted(EXCLUSION_ROLES))}")
    return {
        "ok": present,
        "inverted": True,
        "intended_present": present,
        "exclusions_form": form,
        "exclusion_roles": exclusion_roles,
        "note": note,
    }


def compare_packet(blind_report: Union[dict[str, Any], str],
                   intended: Optional[dict[str, Any]],
                   sid_roster: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """The PHASE-2 (compare) packet: the blind report + the INTENDED OBJECT
    (``meta.contribution_rank``, thesis-like meta keys, exclusions). The seal is
    INVERTED here — the intended object is present by design — so ``seal_check`` is
    :func:`compare_seal_inverted` (proves intent IS present), NOT the SPEC scrub. The
    reader returns a list of typed mismatches whose ``type`` drives the verb law
    (:data:`MISMATCH_TABLE`).

    **The closed section-id vocabulary (W2-S1), ADDITIVE.** ``sid_roster`` is an optional
    ``{sid: title}`` mapping — IDS AND TITLES ONLY, never jobs, never node lists, never
    the plan. When supplied, the prompt names it as a CLOSED vocabulary and constrains
    ``object_key`` to exactly one of: a sid from the roster, a meta key of the intended
    object, or the literal :data:`ARTEFACT_OBJECT_KEY` escape hatch. Without it the reader
    invents its own key ("weighting", "excluded", "Section V") and
    :func:`_resolve_findings_against_plan` — which matches EXACTLY, by design — resolves
    almost nothing, so R10's whole section-kind half banks signal that can never reach an
    actuator. The roster closes that gap at the SOURCE (the reader is told the vocabulary)
    rather than by loosening the match, which is forbidden: no fuzzy, no prefix, no fold —
    ``sec-III`` must never match ``sec-III-quadrature``.

    **The seal is not weakened.** Phase 2 is already inverted for intent
    (:func:`compare_seal_inverted`), and section titles are printed on the rendered pages
    the blind phase read — the roster therefore adds no information the reader had not
    already earned. It adds ADDRESSES, not intent.

    **The escape hatch is what keeps the vocabulary honest.** A closed list with no exit
    would push a mismatch about something ABSENT from the roster onto the nearest sid — a
    silent wrong match minting a real actuator at an innocent section. Instead the reader
    writes :data:`ARTEFACT_OBJECT_KEY`, the mismatch stays fully expressible and banks,
    and the resolver leaves it ``"unresolved"`` so :func:`bank` mints nothing.

    ``sid_roster=None`` (the default) is BYTE-COMPATIBLE with HEAD: same prompt, same
    payload keys, no vocabulary block, no roster keys. An unusable roster (empty,
    malformed, colliding with the meta namespace) RAISES — see
    :func:`_checked_sid_roster`."""
    intended = dict(intended or {})
    intended_json = json.dumps(intended, ensure_ascii=False, indent=2, sort_keys=True)
    blind_json = (blind_report if isinstance(blind_report, str)
                  else json.dumps(blind_report, ensure_ascii=False, indent=2,
                                  sort_keys=True))
    menu = ", ".join(sorted(MISMATCH_TABLE))
    meta_keys = sorted(intended)

    roster: Optional[dict[str, str]] = None
    vocabulary_block = ""
    key_gloss = "<the meta key or the section id it concerns>"
    if sid_roster is not None:
        roster = _checked_sid_roster(sid_roster, meta_keys)
        listing = "\n".join(f"  {sid}  {title}".rstrip()
                            for sid, title in roster.items())
        # WHICH namespace a given mismatch may name is not the reader's to guess: the
        # resolver is namespace-SCOPED by the type's object_kind (C3.4), so a section id
        # written under a meta-kind type resolves to nothing however real the id is. The
        # coupling is read straight off MISMATCH_TABLE — the same table the verb law and
        # the resolver read — so the prompt can never drift from the rule it states.
        _sect = ", ".join(sorted(t for t, r in MISMATCH_TABLE.items()
                                 if r.object_kind == "section"))
        _meta = ", ".join(sorted(t for t, r in MISMATCH_TABLE.items()
                                 if r.object_kind == "meta"))
        vocabulary_block = (
            "=== THE SECTION-ID VOCABULARY (CLOSED — ids and titles only) ===\n"
            f"{listing}\n\n"
            "=== THE META KEYS OF THE INTENDED OBJECT (CLOSED) ===\n"
            f"  {', '.join(meta_keys) if meta_keys else '(none)'}\n\n"
            "OBJECT_KEY RULE — object_key must be EXACTLY one of:\n"
            "  * a section id from the vocabulary above — the ID, copied BYTE-FOR-BYTE; "
            "never the title, never a printed section number ('Section V'), never a "
            "Roman numeral, never an id you infer;\n"
            "  * a meta key from the list above, copied byte-for-byte;\n"
            f'  * the literal "{ARTEFACT_OBJECT_KEY}" — the artefact-kind ESCAPE HATCH.\n'
            "Matching downstream is EXACT and case-sensitive: a near miss, a prefix, a "
            "lowercased or pluralised id resolves to NOTHING.\n"
            "WHICH of the two lists applies is fixed by the TYPE you choose, not by "
            "preference:\n"
            f"  * a SECTION ID is required for: {_sect}\n"
            f"  * a META KEY is required for: {_meta}\n"
            "A section id written under a meta-kind type (or the reverse) resolves to "
            "nothing, however real the id is. If the mismatch you mean does not fit its "
            f'type\'s namespace, write "{ARTEFACT_OBJECT_KEY}" — that is what it is for.\n'
            f'USE "{ARTEFACT_OBJECT_KEY}" whenever the disagreement is about the artefact '
            "AS A WHOLE, or about anything that is not in either list above — a section "
            "the plan never carried, a cross-cutting weighting, a framing with no single "
            "home. Do NOT force such a mismatch onto the nearest section id: a wrong id "
            "is far worse than the hatch. The hatch keeps the mismatch fully expressible "
            "and sends it to the author; a wrong id sends a machine at an innocent "
            "section.\n\n"
        )
        key_gloss = ("<a section id from the vocabulary, a meta key, or "
                     f"{ARTEFACT_OBJECT_KEY}>")

    prompt = (
        f"{COMPARE_INSTRUCTION}\n\n"
        f"=== WHAT YOU RECOVERED BLIND ===\n{blind_json}\n\n"
        f"=== THE INTENDED OBJECT ===\n{intended_json}\n\n"
        f"{vocabulary_block}"
        'Return ONLY JSON: a list of mismatches, each {"type": "<one of: '
        f'{menu}>", "object_key": "{key_gloss}", '
        '"note": "<what disagrees, one line>"}. Empty list if the recovered paper IS '
        "the intended paper on every axis."
    )
    payload: dict[str, Any] = {
        "reader": _RID,
        "organ": "sealed_subagent",
        "phase": "compare",
        "instruction": COMPARE_INSTRUCTION,
        "intended": intended,
        "blind_report": blind_report,
        "mismatch_types": sorted(MISMATCH_TABLE),
        "compare_schema": ["type", "object_key", "note"],
        "seal_inversion": ("PHASE-2 seal is deliberately INVERTED — the intended "
                           "object is present by design; the SPEC/INTENT scrub is not "
                           "applied (comparing against intent is R10's function). See "
                           "restart_reader.compare_seal_inverted."),
        "prompt": prompt,
    }
    if roster is not None:
        payload["sid_roster"] = roster
        payload["object_key_vocabulary"] = {
            "sids": list(roster),
            "meta_keys": meta_keys,
            "escape_hatch": ARTEFACT_OBJECT_KEY,
            "matching": "exact, case-sensitive — no fuzzy, no prefix, no fold",
            "note": ("ids and TITLES only: no jobs, no node lists, no plan. The titles "
                     "are printed on the pages the blind phase already read, so the "
                     "roster adds addresses, not intent."),
        }
    payload["seal_check"] = compare_seal_inverted(payload)
    return payload


# ---------------------------------------------------------------------------
# 4. The verb law — mismatch TYPE → (verb, owned finding-kind, object kind)
# ---------------------------------------------------------------------------
#
# The documented table the acceptance stage rules by. It is SURJECTIVE onto
# ``adjudicate.PROJECTION_VERBS`` — every plan-altitude verb has a mismatch that
# produces it — so the whole verb vocabulary is reachable from a real disagreement:
#
#     mismatch type   verb      owned kind             object   the disagreement
#     ------------------------------------------------------------------------------
#     identity        RESTART   identity-mismatch      meta     wholesale: the recovered
#                                                               paper is a DIFFERENT object
#                                                               — re-plan from the conceptric
#     contribution    RESPINE   identity-mismatch      meta     the primary contribution is
#                                                               not the intended one —
#                                                               re-anchor the apex/spine
#     omission        REOPEN    identity-mismatch      meta     an intended contribution is
#                                                               ABSENT — un-retire it
#     emphasis        DEMOTE    emphasis-mismatch      section  a section is weighted ABOVE
#                                                               its intended rank — lower it
#     order           REORDER   emphasis-mismatch      section  the sequence ≠ intended
#                                                               prominence — re-sequence
#     conflation      SPLIT     emphasis-mismatch      section  two intended-distinct
#                                                               contributions conflated —
#                                                               divide them
#     overreach       CUT       conclusion-overreach   section  the conclusion overclaims vs
#                                                               the evidence — retire it
#     exclusion       CUT       exclusion-violated     section  excluded content is present
#                                                               — cut it

@dataclass(frozen=True)
class MismatchRule:
    verb: str            # a member of adjudicate.PROJECTION_VERBS
    kind: str            # the R10-owned finding-kind (roster.READER_FINDING_KINDS)
    object_kind: str     # "meta" | "section" (make_projection_intent's object kind)
    gloss: str


MISMATCH_TABLE: dict[str, MismatchRule] = {
    "identity":     MismatchRule("RESTART", "identity-mismatch", "meta",
                                 "wholesale: the recovered paper is a different object "
                                 "than intended — re-plan from the conceptric"),
    "contribution": MismatchRule("RESPINE", "identity-mismatch", "meta",
                                 "the primary contribution recovered is not the intended "
                                 "one — re-anchor the apex/spine"),
    "omission":     MismatchRule("REOPEN", "identity-mismatch", "meta",
                                 "an intended contribution is absent from the recovered "
                                 "paper — un-retire it"),
    "emphasis":     MismatchRule("DEMOTE", "emphasis-mismatch", "section",
                                 "a section is weighted above its intended contribution "
                                 "rank — lower its prominence"),
    "order":        MismatchRule("REORDER", "emphasis-mismatch", "section",
                                 "the rhetorical sequence does not match intended "
                                 "prominence — re-sequence"),
    "conflation":   MismatchRule("SPLIT", "emphasis-mismatch", "section",
                                 "two intended-distinct contributions are conflated in "
                                 "one section — divide them"),
    "overreach":    MismatchRule("CUT", "conclusion-overreach", "section",
                                 "the conclusion claims more achieved than the evidence "
                                 "bears — retire the overclaim"),
    "exclusion":    MismatchRule("CUT", "exclusion-violated", "section",
                                 "content the intended object marks as excluded is "
                                 "present — cut it"),
}

#: mismatch type → plan-altitude verb (the surjection onto PROJECTION_VERBS).
VERB_FOR_MISMATCH: dict[str, str] = {t: r.verb for t, r in MISMATCH_TABLE.items()}


# ---------------------------------------------------------------------------
# 5. Bank — one reader-report + a DRAFT projection-intent per mismatch
# ---------------------------------------------------------------------------

def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _feedback_ledger(manuscript_dir: Path) -> Path:
    """The manuscript's feedback ledger (mirrors ``evolution_consumer._feedback_ledger``
    and the registry convention: ``<manuscript>/feedback/feedback.jsonl``)."""
    return manuscript_dir / "feedback" / "feedback.jsonl"


def _mismatches_of(comparison: Any) -> list[dict[str, Any]]:
    """Normalise a comparison verdict to a list of mismatch dicts. Accepts a bare list,
    ``{"mismatches": [...]}``, ``{"findings": [...]}``, or ``{"verdict": [...]}`` — a
    RECOGNISED shape carrying a (possibly empty) list of mismatch dicts.

    An UNRECOGNISED shape RAISES ``ValueError`` (the fail-loud idiom of
    :func:`extract_artefact_text`) rather than returning ``[]`` and letting
    :func:`make_reader_report` certify clean: a whole-artefact judge must never read a
    wrong-shape reply as 'no mismatches'. This is what distinguishes a genuinely-empty
    mismatch list (clean) from a reply whose shape was never parsed (raise) — the
    well-formed-JSON-but-wrong-shape leg that ``verdict_io``'s transport gate does not
    close."""
    raw = comparison
    if isinstance(comparison, dict):
        for key in ("mismatches", "findings", "verdict"):
            if key in comparison:
                raw = comparison[key]
                break
        else:
            raise ValueError(
                "restart_reader: comparison dict carries none of "
                "{mismatches, findings, verdict} — unrecognised shape "
                f"(keys={sorted(comparison)!r}); refusing to read as clean")
    if not isinstance(raw, list):
        raise ValueError(
            "restart_reader: comparison is not a list of mismatches "
            f"(got {type(raw).__name__}); refusing to read as clean")
    for m in raw:
        if not isinstance(m, dict):
            raise ValueError(
                "restart_reader: comparison list holds a non-dict item "
                f"({type(m).__name__}); refusing to read as clean")
    return raw


def _plan_target_namespaces(plan: dict[str, Any]) -> tuple[set[str], set[str]]:
    """The two namespaces an R10 mismatch's ``object_key`` can name in the LIVE plan:
    the section ids (``schema.plan_sections`` — the ``section``-kind actuators' targets)
    and the ``plan.meta`` keys (the ``meta``-kind actuators' targets). A key in NEITHER
    is UNADDRESSABLE — the projection-intent it would mint points at no live target, so
    C3.4 refuses to mint it (the finding still banks; the actuator does not).

    Raises on a structurally-defective plan (``meta`` not a mapping, ``sections`` not a
    list of dicts, …). :func:`_resolve_findings_against_plan` catches that and degrades
    to EMPTY namespaces rather than letting it escape — see
    :data:`PLAN_UNREADABLE_BASIS`."""
    from laplace.pipeline import schema
    sids = {sid for sec in schema.plan_sections(plan) if (sid := sec.get("id"))}
    meta_keys = set((plan.get("meta") or {}).keys())
    return sids, meta_keys


#: The ``resolution_basis`` stamped on every finding when the supplied plan is
#: STRUCTURALLY UNREADABLE — JSON-shaped but not plan-shaped (``meta`` not a mapping,
#: ``sections`` carrying a non-dict, …). See :func:`_resolve_findings_against_plan`.
PLAN_UNREADABLE_BASIS = "plan-unreadable"


def _resolve_findings_against_plan(findings: list[dict[str, Any]],
                                   plan: dict[str, Any]) -> None:
    """Stamp each finding's ``resolution`` against the LIVE plan (C3.4), NAMESPACE-SCOPED
    by the mismatch TYPE's ``object_kind`` — the same kind that fixes the minted intent's
    actuator (:func:`bank` reads ``rule.object_kind``, defaulting ``"meta"`` for an
    unknown type). A ``meta``-kind mismatch resolves ONLY against ``plan.meta`` keys; a
    ``section``-kind mismatch resolves ONLY against the section ids. Matching is EXACT and
    CASE-SENSITIVE (Python ``in`` on the key set — no normalisation, no fold).

    A key that exists solely in the OTHER namespace is ``"unresolved"``, not resolved: a
    ``contribution`` mismatch (``object_kind=meta``) whose ``object_key`` happens to name a
    real section id does NOT resolve, because the intent it would mint is a meta-kind
    actuator that would point at a section — the cross-namespace false positive the union
    test admitted. This is the SAME fail-closed refusal already proven for unknown keys:
    unresolved is flagged, banks its signal, and mints no intent in :func:`bank`.

    A finding whose ``where`` (the mismatch ``object_key``) names a real key in ITS OWN
    namespace resolves (``"resolved"``); anything else — an empty key, an unknown key, or a
    key living only in the sibling namespace — is ``"unresolved"``. Mutates in place. Called
    ONLY when a plan is supplied; ``plan=None`` leaves findings untouched (no ``resolution``
    key), byte-identical to HEAD.

    :data:`ARTEFACT_OBJECT_KEY` — the compare packet's artefact-kind escape hatch — needs
    NO special case here and gets none: it names no sid and no meta key, so it falls out
    ``"unresolved"`` under the same rule as any other unaddressable key, banking its
    signal and minting no actuator. That is precisely what the hatch is for, and it is why
    a mismatch about something ABSENT from the roster can be said without being forced
    onto a wrong section.

    **An UNREADABLE plan degrades, it does not destroy.** A plan that is JSON-shaped but
    not plan-shaped (``meta`` not a mapping, ``sections`` carrying a non-dict, …) made
    :func:`_plan_target_namespaces` raise, and because :func:`bank` resolves BEFORE it
    appends, that raise took the whole reader-report with it — both phases and every
    finding of a dispatched blind+compare read, lost to an untyped ``AttributeError``.
    That is the exact inverse of this stage's law. So the defect is caught here and the
    namespaces degrade to EMPTY: every finding stamps ``"unresolved"`` (the signal banks,
    NO actuator mints) and carries ``resolution_basis`` naming the plan defect, so the
    degradation is loud in the ledger instead of silent. Nothing certifies clean on this
    path — ``clean`` is decided by the mismatch count, which the plan never touches."""
    try:
        sids, meta_keys = _plan_target_namespaces(plan)
        basis = ""
    except Exception as exc:                        # JSON-shaped, not plan-shaped
        sids, meta_keys = set(), set()
        basis = f"{PLAN_UNREADABLE_BASIS}: {type(exc).__name__}: {exc}"
    for f in findings:
        where = str(f.get("where") or "")
        rule = MISMATCH_TABLE.get(f.get("mismatch_type") or "")
        object_kind = rule.object_kind if rule else "meta"   # mirrors bank's own default
        namespace = meta_keys if object_kind == "meta" else sids
        f["resolution"] = "resolved" if where and where in namespace else "unresolved"
        if basis:
            f["resolution_basis"] = basis


def _mismatch_finding(m: dict[str, Any]) -> dict[str, Any]:
    """One mismatch as a reader-finding in the standard shape (stamped R10 + routed via
    the roster), carrying its ``mismatch_type`` and a deterministic ``id`` the
    projection-intent targets. An unknown mismatch type keeps the coarsest kind
    (``identity-mismatch``) — never dropped."""
    from laplace.pipeline.ledger import finding_id

    mtype = str(m.get("type", "")).strip()
    rule = MISMATCH_TABLE.get(mtype)
    kind = rule.kind if rule else "identity-mismatch"
    where = str(m.get("object_key") or m.get("where") or "").strip()
    issue = str(m.get("note") or (rule.gloss if rule else "")).strip()
    f = reader_finding(_RID, where, issue, None, kind,
                       quote=(str(m.get("quote", "")).strip() or None))
    f["mismatch_type"] = mtype
    f["id"] = finding_id(f)
    return f


# ---------------------------------------------------------------------------
# reader BLINDNESS provenance (WO-20260820-reader-blindness-provenance)
#
# Phase 1 is a BLIND read, but the blindness is a property of the READER, not of
# this module: the packet can deny the plan, it cannot deny what the reader saw
# before it opened the packet. A dispatched reader that had already seen a work
# order naming the artefact, a prior return, or a directory listing that gestures
# at the content is CONTAMINATED — and until now the record carried no field to
# say so, so a named contamination died with the session return and the ledger
# read as though every blind read had been clean. This is the field.
#
# It is PROVENANCE ABOUT THE READ, never a verdict about the artefact: it does
# not touch ``clean`` (a contaminated reader can still find real mismatches, and
# a consumer that wants to discount the run reads this field to do it).
# ---------------------------------------------------------------------------

#: the claims a reader may make about its own blindness. ``undisclosed`` is not a
#: claim — it is what the ABSENCE of one reads as.
BLINDNESS_CLAIMS: tuple[str, ...] = ("clean", "contaminated")

#: what a record with NO blindness field means: LEGACY-UNDISCLOSED. Never ``clean``
#: — every R10 record banked before this field existed, and every run whose reader
#: said nothing, is a read whose blindness was never established.
UNDISCLOSED_BLINDNESS: dict[str, Any] = {
    "claimed": "undisclosed", "disclosures": [], "disclosed": False}


def normalize_blindness(blindness: Any) -> dict[str, Any]:
    """The typed blindness record: ``{claimed, disclosures, disclosed}`` (+
    ``claimed_raw`` when a claim was unrecognised, ``downgraded`` when a claim was
    overruled). FAIL-CLOSED on three axes:

      * **absent** — ``None`` / ``{}`` / anything unrecognised reads as
        ``undisclosed``, NEVER as clean.
      * **unrecognised claim** — a ``claimed`` outside :data:`BLINDNESS_CLAIMS` reads
        as ``undisclosed``, with the raw string kept in ``claimed_raw`` rather than
        guessed at.
      * **contradiction** — a ``clean`` claim that carries disclosures is DOWNGRADED
        to ``contaminated``. What the reader listed outranks what the reader claimed;
        a read that names an exposure is not a clean read however it is labelled.

    Accepts the dict form (``{claimed, disclosures}``; ``claim``/``exposures`` are
    read as aliases), a bare claim string, or a bare list of disclosures."""
    claimed_raw: Any = None
    disclosures: list[str] = []
    if isinstance(blindness, dict):
        claimed_raw = blindness.get("claimed", blindness.get("claim"))
        raw_d = blindness.get("disclosures", blindness.get("exposures"))
        if isinstance(raw_d, (str, bytes)):
            raw_d = [raw_d]
        for d in (raw_d or []):
            s = str(d).strip()
            if s:
                disclosures.append(s)
    elif isinstance(blindness, str):
        claimed_raw = blindness
    elif isinstance(blindness, (list, tuple)):
        disclosures = [s for d in blindness if (s := str(d).strip())]
        claimed_raw = "contaminated" if disclosures else None

    claimed = str(claimed_raw or "").strip().casefold()
    out: dict[str, Any] = dict(UNDISCLOSED_BLINDNESS)
    out["disclosures"] = disclosures
    if claimed not in BLINDNESS_CLAIMS:
        if claimed:
            out["claimed_raw"] = str(claimed_raw)
        return out
    if claimed == "clean" and disclosures:            # the listing outranks the label
        out.update({"claimed": "contaminated", "disclosed": True,
                    "downgraded": "clean claim carries disclosures"})
        return out
    out.update({"claimed": claimed, "disclosed": True})
    return out


def blindness_of(record: Any) -> dict[str, Any]:
    """The blindness of ANY banked R10 record — including one banked before the field
    existed, which reads as legacy-undisclosed (never clean)."""
    return normalize_blindness((record or {}).get("blindness")
                               if isinstance(record, dict) else None)


def make_reader_report(blind_report: Any, comparison: Any, *, project: str = "",
                       round: int = 0, rec_id: Optional[str] = None,
                       ts: Optional[str] = None,
                       truncated: bool = False,
                       blindness: Any = None,
                       plan: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """The one ``reader-report`` record: ``record='reader-report'``, ``reader='R10'``,
    both phases banked (``phases={blind, compare}``), and the per-mismatch findings
    (each with the deterministic id its projection-intent targets). ``clean`` is
    deterministic, never an agent claim (the ``verdict_io`` idiom), and fail-closed on
    two axes:

      * **parse** — a wrong-shape ``comparison`` RAISES in :func:`_mismatches_of`, so a
        reply whose shape was never parsed can never reach the clean bit below; only a
        recognised shape (including a genuinely-empty list) does.
      * **truncation** — a ``truncated`` blind read never met the WHOLE artefact, so it
        may not certify a clean whole-artefact verdict even with zero mismatches (the
        ``blind_packet`` ``truncated`` flag rides in from the caller).

    **Blindness provenance.** ``blindness`` records what the phase-1 reader disclosed
    about its OWN blindness (:func:`normalize_blindness`); the record ALWAYS carries the
    field, and an absent / unrecognised / self-contradicting claim reads as
    ``undisclosed`` or ``contaminated``, never as clean. It is provenance about the
    READ and deliberately does not enter the ``clean`` bit — a contaminated reader's
    mismatches are still real findings; what changes is how much a later reconstruction
    should trust a *clean* verdict from that run.

    **Target resolution (C3.4).** When ``plan`` is supplied, each finding is stamped with
    a ``resolution`` against the LIVE plan, NAMESPACE-SCOPED by the mismatch type's
    ``object_kind``: a ``meta``-kind mismatch's ``where`` (mismatch ``object_key``) is
    ``"resolved"`` only when it names a real ``plan.meta`` key; a ``section``-kind
    mismatch's ``where`` only when it names a real section id. Matching is EXACT and
    CASE-SENSITIVE. A key in the OTHER namespace (or none) is ``"unresolved"``.
    :func:`bank` mints a projection-intent ONLY for a resolved finding —
    an unresolved (unaddressable) actuator is refused while its finding still banks. The
    ``resolution`` stamp lands AFTER the deterministic id, so it never perturbs the id an
    intent targets. ``plan=None`` (the additive default) leaves every finding untouched —
    byte-identical to HEAD. A supplied plan that is JSON-shaped but NOT plan-shaped
    degrades to empty namespaces (everything ``"unresolved"`` + a ``resolution_basis``)
    rather than raising and taking the whole report with it."""
    now = ts or _now()
    findings = [_mismatch_finding(m) for m in _mismatches_of(comparison)]
    if plan is not None:
        _resolve_findings_against_plan(findings, plan)
    from laplace.pipeline.ledger import finding_id
    rid = rec_id or ("R10-report-" + finding_id(
        {"reader": _RID, "record": "reader-report", "phases_blind": blind_report,
         "findings": [f["id"] for f in findings]}))
    clean = (not truncated) and len(findings) == 0
    verdict = ("clean" if clean
               else "identity-mismatch" if findings
               else "truncated")
    return {
        "id": rid,
        "record": "reader-report",
        "reader": _RID,
        "project": project,
        "ts": now,
        "dimension": READERS[_RID].dimension,
        "panel_label": READERS[_RID].panel_label,
        "status": "open",
        "clean": clean,
        "truncated": bool(truncated),
        "blindness": normalize_blindness(blindness),
        "phases": {"blind": blind_report, "compare": comparison},
        "findings": findings,
        "provenance": {"actor": _ACTOR,
                       "verdict": verdict,
                       "round": round, "ts": now},
    }


def bank(manuscript_dir: Union[str, Path], blind_report: Any, comparison: Any, *,
         project: str = "", round: int = 0, truncated: bool = False,
         blindness: Any = None,
         feedback_path: Optional[Union[str, Path]] = None,
         plan: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Bank R10's verdict through the one locked door (``ledger.append_jsonl`` — the
    append-only, file-locked write the engine offers):

      (a) ONE ``reader-report`` record (both phases + the per-mismatch findings);
      (b) for each mismatch, a DRAFT ``projection-intent`` via
          ``adjudicate.make_projection_intent`` — actor ``R10:restart-reader``, the verb
          drawn from :data:`MISMATCH_TABLE` (draft-only law: queued, never executed; the
          evolution consumer drafts a plan proposal and the author ratifies).

    **Target resolution (C3.4).** When ``plan`` is supplied it is threaded into
    :func:`make_reader_report`, which stamps each finding's ``resolution`` against the
    live plan, NAMESPACE-SCOPED by the mismatch type's ``object_kind`` (meta-kind resolves
    against ``plan.meta`` keys only, section-kind against section ids only; exact,
    case-sensitive). Step (b) then mints a projection-intent
    ONLY for a ``"resolved"`` finding; an ``"unresolved"`` finding is banked in the report
    but its unaddressable actuator is REFUSED — the signal is kept, no intent points at a
    target the plan does not carry. ``plan=None`` (the additive default) resolves nothing
    and mints every finding's intent exactly as HEAD does. A structurally-unreadable plan
    banks the report with every finding ``"unresolved"`` and zero intents — it never costs
    the reader its banked read.

    **Blindness provenance.** ``blindness`` — what the phase-1 reader disclosed about
    its own exposure ({claimed: clean|contaminated, disclosures: [...]}) — is threaded
    into the reader-report, which ALWAYS carries the normalised field. Absent reads as
    ``undisclosed``, never clean (:func:`normalize_blindness`), so a contaminated read
    can no longer bank as though it had been blind.

    Returns ``{report, intents, path, n_findings, clean}``. ``truncated`` (the
    ``blind_packet`` flag) forbids a clean verdict — a truncated whole-artefact read
    never certifies. ``feedback_path`` overrides the default
    ``<manuscript>/feedback/feedback.jsonl`` (used by tests)."""
    from laplace.pipeline import adjudicate, ledger

    mdir = Path(manuscript_dir)
    path = Path(feedback_path) if feedback_path else _feedback_ledger(mdir)
    report = make_reader_report(blind_report, comparison, project=project, round=round,
                                truncated=truncated, blindness=blindness, plan=plan)
    ledger.append_jsonl(path, report)                # (a) the one reader-report

    intents: list[dict[str, Any]] = []
    for f in report["findings"]:
        if f.get("resolution") == "unresolved":      # C3.4: unaddressable actuator refused
            continue                                 # (the finding still banked above)
        rule = MISMATCH_TABLE.get(f.get("mismatch_type") or "")
        verb = rule.verb if rule else "CUT"          # unknown → safest retire (mirrors
        object_kind = rule.object_kind if rule else "meta"   # make_projection_intent's own default)
        intent = adjudicate.make_projection_intent(
            f["id"], verb, object_kind=object_kind,
            object_key=str(f.get("where") or ""),
            note=str(f.get("issue") or ""),
            finding_kind=str(f.get("kind") or ""),
            section=str(f.get("section") or ""),
            actor=_ACTOR, round=round, project=project)
        ledger.append_jsonl(path, intent)            # (b) a DRAFT projection-intent
        intents.append(intent)

    return {"report": report, "intents": intents, "path": str(path),
            "n_findings": len(report["findings"]), "clean": report["clean"]}
