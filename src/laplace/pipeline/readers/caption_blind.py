"""R9 Caption-blind — the sealed CAPTION-ONLY reader (the hold-out review surface).

His spec (2026-07-10 hold-out review): *"Give a reviewer only the figure and caption.
They must identify: the supported claim; the evidence type in every panel; the
limitation. If they cannot, the surface fails."*

A figure that carries its weight is legible from **caption + image alone** — the body
prose is a courtesy, not a crutch. This reader is the mechanical proof of that: it
meets each figure with ONLY its rendered crop and its caption text, and must recover
three things per figure —

    * the CLAIM the figure supports,
    * the EVIDENCE TYPE in each panel (proof / measurement / simulation / schematic),
    * the figure's stated LIMITATION / scope.

A figure where the blind reader CANNOT name the claim, an evidence type, or the
limitation is a **FAILED figure** — the caption is doing too little or the figure too
much. Failures pour through the hardened door as figure-routed findings and surface in
the escalation queue for his ruling.

**The seal is the point.** A caption-blind reader that can see the body is worthless —
the isolation is what makes the surface a test. So the input is CONSTRUCTED to carry
only (caption text, figure crop): the caption is extracted from the flattened,
comment-stripped manuscript (the ``% <sid>-pN`` provenance thread is already gone),
the body prose is never gathered into the payload, and :func:`caption_blind_seal`
re-checks the packed input against the spec/provenance sentinels so a regression that
let the body or the provenance leak in is caught.

Following the reader-suite pattern (visual.py / sealed.py): this module PACKAGES the
read and PARSES the verdict — it does NOT call a model. Phase F / the lock run drives
the multimodal call at candidate-lock. It reuses the Phase-D2 ``visual_gate``
figure crop wholesale (``insp.views['figure_crops']`` — the A3/F1F2-corrected
per-column crop, NOT re-cut here) and pairs each crop with its caption. FAILED figures
are banked via :func:`pour_caption_blind` → ``ledger.pour_finding`` (id + section
anchor mandatory, idempotent).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline.apparatus_common import section_of, section_spans
from laplace.pipeline.caption_audit import _extract_caption, _FLOAT_RE, _LABEL_RE
from laplace.pipeline.readers.roster import READERS, reader_finding
from laplace.pipeline.readers.sealed import _coerce_json, seal_holds

_RID = "R9"


# ---------------------------------------------------------------------------
# The lens — the caption-blind instruction and the return schema
# ---------------------------------------------------------------------------

CAPTION_BLIND_INSTRUCTION = (
    "You are a reviewer given ONLY a figure and its caption — NOT the body of the "
    "paper, NOT the section it sits in, NOT any provenance or build note. Judge the "
    "figure on the caption and the pixels alone. For EACH figure you are shown, "
    "recover THREE things and say plainly whether you can: (1) the CLAIM the figure "
    "supports (the one thing it is evidence for); (2) the EVIDENCE TYPE in EACH panel "
    "— is it a proof, a measurement, a simulation, or a schematic; (3) the figure's "
    "stated LIMITATION or scope (what it does NOT show / where it does not hold). "
    "If you CANNOT name the claim, cannot read a panel's evidence type, or cannot find "
    "the limitation FROM THE CAPTION AND IMAGE ALONE, that figure FAILS — do not "
    "reconstruct it from what you happen to know about the field. Report confusion, "
    "not charity."
)

_RETURN_SCHEMA = (
    'Return ONLY JSON: a list, one object per figure, each '
    '{"where": "<figure label>", "identifiable": <true|false>, '
    '"claim": "<the claim, or \\"unclear\\" if you cannot name it>", '
    '"evidence": ["<evidence type per panel>", ...], '
    '"limitation": "<the stated limitation, or \\"unclear\\">", '
    '"issue": "<what a reader cannot recover>", "fix": "<smallest caption change>"}. '
    "Set identifiable=false for any figure whose claim, a panel's evidence type, or "
    "limitation you could not recover from the caption+image alone."
)


# ---------------------------------------------------------------------------
# Caption extraction — the caption text per figure, isolated from the body
# ---------------------------------------------------------------------------

def figure_captions(target: Union[str, Path]) -> dict[str, dict[str, str]]:
    """``label -> {caption, section}`` for every float in the manuscript. The
    caption is the balanced-brace ``\\caption{...}`` body (reusing
    ``caption_audit._extract_caption``, so nested math braces do not miscount); the
    section is the slug of the ``\\section`` the float sits under (the plain anchor
    for the pour). Read from ``_gather_manuscript_text`` — flattened along ``\\input``
    and COMMENT-STRIPPED, so the ``% <sid>-pN`` provenance thread is gone before a
    caption is ever cut. The BODY prose is never returned — only captions."""
    full = _gather_manuscript_text(target)
    spans = section_spans(full)
    out: dict[str, dict[str, str]] = {}
    for m in _FLOAT_RE.finditer(full):
        env, _star, body = m.group(1), m.group(2), m.group(3)
        pos = m.start()
        slug, _title, _app = section_of(pos, spans)
        lab_m = _LABEL_RE.search(body)
        label = lab_m.group(1) if lab_m else f"{env}@{pos}"
        cap = _extract_caption(body) or ""
        out[label] = {"caption": re.sub(r"\s+", " ", cap).strip(),
                      "section": slug or ""}
    return out


# ---------------------------------------------------------------------------
# The seal — caption+image bytes ONLY (no body, no provenance)
# ---------------------------------------------------------------------------

#: Sentinels that would betray the body prose leaking into a caption-only payload.
#: A genuine caption never carries a section heading or a bare body cross-reference
#: as its content; the spec/provenance sentinels are covered by ``sealed.seal_holds``.
_BODY_SENTINELS: tuple[str, ...] = (
    r"\section{", r"\subsection{", r"\begin{abstract}", r"\paragraph{",
)


def caption_blind_seal(payload: dict[str, Any]) -> dict[str, Any]:
    """Prove the packed payload carries caption+image ONLY. Two checks: (i) the
    spec/provenance sentinels (delegated to ``sealed.seal_holds`` — the shared seal
    surface, so a provenance leak into a caption is caught the same way it is for the
    sealed readers); (ii) the BODY sentinels above (a section heading / abstract
    environment must never appear in a caption-only input). Returns
    ``{ok, leaks}``."""
    base = seal_holds(payload)
    leaks = list(base["leaks"])
    hay = (payload.get("sealed_input", "") or "") + "\n" + (payload.get("prompt", "") or "")
    for s in _BODY_SENTINELS:
        if s in hay:
            leaks.append({"sentinel": s, "where": "body-leak"})
    return {"ok": not leaks, "leaks": leaks}


# ---------------------------------------------------------------------------
# Package the read — reuse the D2 figure crop, pair it with the caption
# ---------------------------------------------------------------------------

def pack_caption_blind(insp: "Any", target: Union[str, Path]) -> dict[str, Any]:
    """Package the caption-blind read: for each Phase-D2 figure crop
    (``insp.views['figure_crops']`` — the A3/F1F2-corrected per-column crop, reused
    verbatim), pair the crop image with its caption TEXT and NOTHING else. The
    ``sealed_input`` is the captions alone (never the body); the images ride
    ``payload['images']`` for the driver to attach. Phase F supplies the vision model
    and calls :func:`parse_caption_blind_verdict`; this module never calls a model."""
    caps = figure_captions(target)
    figures: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    sealed_parts: list[str] = []
    for e in insp.views.get("figure_crops", []):
        label = e.get("label")
        info = caps.get(label, {})
        caption = info.get("caption", "")
        figures.append({"label": label, "caption": caption,
                        "section": info.get("section", ""),
                        "image": {"path": e["path"], "page": e.get("page")}})
        images.append({"view": "figure_crops", "path": e["path"],
                       "label": label, "page": e.get("page")})
        sealed_parts.append(f"[{label}]\n{caption or '(no caption)'}")
    sealed_input = "\n\n".join(sealed_parts)
    prompt = (f"{CAPTION_BLIND_INSTRUCTION}\n\n"
              "THE CAPTIONS (each paired with the figure image of the same label):\n"
              f"{sealed_input}\n\n{_RETURN_SCHEMA}")
    payload: dict[str, Any] = {
        "reader": _RID,
        "organ": "rasteriser",
        "instruction": CAPTION_BLIND_INSTRUCTION,
        "prompt": prompt,
        "allowed_kinds": list(READERS[_RID].owned_kinds),
        "finding_schema": ["where", "issue", "fix", "kind"],
        "seal": {"denies": list(READERS[_RID].seal_denies),
                 "allows": list(READERS[_RID].seal_allows),
                 "statement": READERS[_RID].seal},
        "figures": figures,
        "images": images,
        "sealed_input": sealed_input,
    }
    payload["seal_check"] = caption_blind_seal(payload)
    return payload


def to_content_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The sealed prompt as one text content block (symmetry with
    ``sealed.to_content_blocks``); the figure images ride ``payload['images']`` for
    the multimodal driver to attach alongside."""
    return [{"type": "text", "text": payload["prompt"]}]


def section_by_label(target: Union[str, Path]) -> dict[str, str]:
    """``label -> section slug`` — the pour's anchor map, so a figure finding whose
    ``where`` is a bare label still pours with a plain section anchor."""
    return {lab: info.get("section", "")
            for lab, info in figure_captions(target).items()}


# ---------------------------------------------------------------------------
# Parse the verdict — a FAILED figure yields one finding per missing facet
# ---------------------------------------------------------------------------

_UNCLEAR = {"", "unclear", "unknown", "n/a", "na", "none", "not stated",
            "unidentifiable", "cannot tell", "can't tell", "cant tell",
            "not identifiable", "?"}


def _is_unclear(v: Any) -> bool:
    s = str(v or "").strip().lower()
    return s in _UNCLEAR or s.startswith("cannot") or s.startswith("can't")


def _missing_facets(claim: str, evidence: Any, limitation: str,
                    identifiable: Any) -> list[tuple[str, str, str]]:
    """Which of (claim, evidence, limitation) a figure FAILS to make identifiable —
    each as ``(kind, issue, fix)``. A facet fails when its value is empty / an
    unclear sentinel; evidence fails when the list is empty or any panel entry is
    unclear. If the reader flagged ``identifiable: false`` but named every facet, the
    claim is treated as the primary miss (the reader disbelieves its own recovery)."""
    missing: list[tuple[str, str, str]] = []
    if _is_unclear(claim):
        missing.append(("caption-blind-claim",
                        "the supported claim is not identifiable from caption+image alone",
                        "state, in the caption, the one claim the figure is evidence for"))
    ev_ok = (isinstance(evidence, list) and len(evidence) > 0
             and all(not _is_unclear(e) for e in evidence))
    if not ev_ok:
        missing.append(("caption-blind-evidence",
                        "a panel's evidence type is not identifiable from caption+image alone",
                        "name each panel's evidence type (proof/measurement/simulation/"
                        "schematic) in the caption"))
    if _is_unclear(limitation):
        missing.append(("caption-blind-limitation",
                        "the figure's stated limitation/scope is absent from the caption",
                        "state the figure's limitation or scope (what it does not show) "
                        "in the caption"))
    if identifiable is False and not missing:
        missing.append(("caption-blind-claim",
                        "the reader could not stand behind the figure's claim from "
                        "caption+image alone",
                        "tighten the caption so the claim is unambiguous from the figure"))
    return missing


def parse_caption_blind_verdict(raw: str, strict: bool = False) -> list[dict[str, Any]]:
    """Parse R9's reply into findings, one per missing facet of each FAILED figure,
    stamped R9 and routed to ``figures`` (via :func:`roster.reader_finding`). A figure
    the reader could fully recover (claim + every panel's evidence + limitation, and
    not ``identifiable: false``) yields NO finding — it PASSED. Each finding carries
    the reader's blind recovery (``blind_claim`` / ``blind_evidence`` /
    ``blind_limitation``) so his escalation view sees exactly what the surface leaked.
    Malformed input → ``[]`` (never a crash). ``strict`` currently only affects the
    empty-input tolerance shared with the other organs."""
    data = _coerce_json(raw)
    if isinstance(data, dict):
        data = data.get("figures", data.get("findings", data.get("verdict", [])))
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        where = str(item.get("where", "")).strip()
        claim = str(item.get("claim", "")).strip()
        evidence = item.get("evidence")
        limitation = str(item.get("limitation", "")).strip()
        identifiable = item.get("identifiable")
        missing = _missing_facets(claim, evidence, limitation, identifiable)
        if not missing:
            continue                                  # PASS — the figure is self-sufficient
        for kind, issue, fix in missing:
            rec = reader_finding(_RID, where, issue, fix, kind,
                                 quote=(str(item.get("caption", "")).strip() or None))
            rec.update({
                "identifiable": False,
                "blind_claim": claim or None,
                "blind_evidence": evidence if isinstance(evidence, list) else None,
                "blind_limitation": limitation or None,
            })
            out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Pour — bank FAILED figures through the hardened door
# ---------------------------------------------------------------------------

def pour_caption_blind(feedback_path: Union[str, Path], findings: list[dict[str, Any]],
                       *, project: str = "", default_section: Optional[str] = None,
                       sections: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Bank R9's FAILED-figure findings through ``ledger.pour_finding`` — the one
    door (id MANDATORY + section anchor + IDEMPOTENCE), never ``append_jsonl``. The
    section anchor for a figure finding is resolved, in order, from: the finding's own
    ``section``; the ``sections`` map (``label -> section``, from
    :func:`section_by_label`); a leading ``N<k>`` token in ``where``; then
    ``default_section``. A finding with no locatable section is REFUSED by the door
    (recorded, not raised). Returns ``{poured, idempotent, refused, refusals}``."""
    from laplace.pipeline.ledger import pour_finding, read_jsonl

    sections = sections or {}
    poured = idempotent = refused = 0
    refusals: list[str] = []
    before = len(read_jsonl(feedback_path)) if Path(feedback_path).is_file() else 0
    for f in findings:
        if not isinstance(f, dict):
            continue
        sec = (f.get("section") or sections.get(f.get("where", "")) or default_section)
        try:
            pour_finding(feedback_path, f, section=sec, project=project, source=_RID)
        except ValueError as e:
            refused += 1
            refusals.append(str(e))
            continue
        after = len(read_jsonl(feedback_path))
        if after > before:
            poured += 1
            before = after
        else:
            idempotent += 1
    return {"poured": poured, "idempotent": idempotent,
            "refused": refused, "refusals": refusals}
