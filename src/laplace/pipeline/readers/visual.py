"""R5 Figure-first + R6 Visual — two readers over ONE set of Phase-D2 crops.

The rasteriser organ (``visual_gate``) already cuts the mandatory views from a
compiled PDF. R5 and R6 share those crops but ask conjugate questions:

    * R5 Figure-first — the figure+caption crops, MEANING lens: does each figure have
      a single principal function, is there construction debris in it, is the caption
      a mini-paper? Owns #3/#4/#5. Findings route to ``figures``.
    * R6 Visual — the full-page / reading / equation crops, GEOMETRY lens:
      collision, tiny label, clipped equation, float misplacement, crowding — the
      geometry defects the compile LOG cannot locate. Owns #7/#12. Findings route
      to ``document``. NOT overflow: log-locatable overfull is owned by the
      mechanical panel (``mech.overfull_floor_pt`` dial), and R6 never re-inspects
      it — the retargeted scope, enforced mechanically in ``visual_gate``.

R6 IS the Phase-D2 vision judge — it reuses ``visual_gate``'s (retargeted)
instruction, vision kinds, and parser wholesale; this module only stamps the R6
reader identity and re-checks the inverse seal (it must NOT be told the layout is
acceptable). R5 reuses the SAME ``figure_crops`` but supplies the MEANING instruction
and R5's kinds. Neither module calls a model — PACKAGE + PARSE, Phase F drives the
multimodal read at candidate-lock. R5's mechanical FLOOR reuses the caption/figure
scaffold-scrub + caption-completeness gates (every round, no model).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline import visual_gate as vg
from laplace.pipeline.readers.roster import READERS, reader_finding
from laplace.pipeline.readers.sealed import seal_holds

# ---------------------------------------------------------------------------
# R5 Figure-first — the MEANING lens over the figure+caption crops
# ---------------------------------------------------------------------------

FIGURE_MEANING_INSTRUCTION = (
    "You are a physicist inspecting the FIGURES of a manuscript for MEANING, not "
    "typesetting. You are shown each figure with its caption, as rendered — not the "
    "source, not the spec that built it. For each figure ask: (1) does it have ONE "
    "principal function, or is it trying to do several things at once "
    "(figure-not-singular)? (2) is there construction DEBRIS left in it — a "
    "'Schematic'/'DIDACTIC'/'Exact' type-tag, a provenance or evidence-class label, "
    "a decorative arrow, a non-claim annotation (figure-debris)? (3) is the CAPTION "
    "a mini-paper — restating the spec, asking the generating questions, more than "
    "what-is-shown / how / one observation / one qualification (caption-mini-paper)? "
    "Judge only what the pixels show. Return ONLY JSON: a list of findings, each "
    '{"where": "<figure label/page>", "issue": "<what is wrong>", "fix": "<smallest '
    'change>", "kind": "<figure-not-singular|figure-debris|caption-mini-paper>"}. '
    "Empty list if every figure is singular, debris-free, and captioned tightly."
)


def _figure_seal_check(instruction: str) -> dict[str, Any]:
    """R5 is sealed from the figure SPEC — the instruction must carry no spec /
    epistemic-labels / type_tag language as an instruction to the reader."""
    return seal_holds({"prompt": instruction, "sealed_input": ""})


def pack_figure_meaning(insp: "vg.Inspection") -> dict[str, Any]:
    """R5 — package the figure+caption crops from a Phase-D2 inspection with the
    MEANING instruction and R5's kinds. Reuses ``insp.views['figure_crops']`` (the
    same crops R6/the D2 gate produced); supplies the conjugate question. Phase F
    hands the images + this instruction to the vision model and calls
    :func:`parse_figure_verdict`."""
    images: list[dict[str, Any]] = []
    for e in insp.views.get("figure_crops", []):
        images.append({"view": "figure_crops", "path": e["path"],
                       "label": e.get("label"), "page": e.get("page")})
    payload = {
        "reader": "R5",
        "organ": "rasteriser",
        "instruction": FIGURE_MEANING_INSTRUCTION,
        "prompt": FIGURE_MEANING_INSTRUCTION,
        "allowed_kinds": list(READERS["R5"].owned_kinds),
        "finding_schema": ["where", "issue", "fix", "kind"],
        "seal": {"denies": list(READERS["R5"].seal_denies),
                 "allows": list(READERS["R5"].seal_allows),
                 "statement": READERS["R5"].seal},
        "images": images,
    }
    payload["seal_check"] = _figure_seal_check(FIGURE_MEANING_INSTRUCTION)
    return payload


def figure_floor(target: Union[str, Path],
                 project: Optional[str] = None) -> list[dict[str, Any]]:
    """R5 — the mechanical floor, every round, no model: the caption/figure
    scaffold-scrub (``scaffold_wipe.check_caption_scaffold``) catches type-tag /
    generating-question debris in captions before the vision read is spent, and
    ``caption_audit.check_caption_completeness`` catches a caption that fails to name
    its object. Findings keep their native kinds (owned by the figures stage / C5),
    stamped ``reader='R5', floor=True`` — the floor R5 sits on, not R5's owned
    vision kinds."""
    from laplace.pipeline.caption_audit import check_caption_completeness
    from laplace.pipeline.scaffold_wipe import check_caption_scaffold

    out: list[dict[str, Any]] = []
    try:
        for f in check_caption_scaffold(target):
            out.append({**f, "reader": "R5", "floor": True})
    except Exception as e:  # noqa: BLE001 — a scrub crash is a loud floor signal
        out.append(reader_finding("R5", "captions", f"caption scaffold scrub failed: {e}",
                                  None, "figure-debris") | {"floor": True, "failed": True})
    try:
        res = check_caption_completeness(target)
        for f in res.get("findings", []):
            out.append({**f, "reader": "R5", "floor": True})
    except Exception:  # noqa: BLE001
        pass
    return out


def parse_figure_verdict(raw: str, strict: bool = False) -> list[dict[str, Any]]:
    """Parse R5's vision verdict into findings stamped R5, routed to ``figures``.
    Unknown/missing kind coerces to ``figure-not-singular`` (still figures-routed)
    unless ``strict``. Malformed → ``[]``."""
    from laplace.pipeline.readers.sealed import _coerce_json
    data = _coerce_json(raw)
    if isinstance(data, dict):
        data = data.get("findings", data.get("verdict", []))
    if not isinstance(data, list):
        return []
    allowed = set(READERS["R5"].owned_kinds)
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip()
        if kind not in allowed:
            if strict:
                continue
            kind = "figure-not-singular"
        out.append(reader_finding(
            "R5", str(item.get("where", "")).strip(),
            str(item.get("issue", "")).strip(),
            (str(item.get("fix", "")).strip() or None), kind))
    return out


# ---------------------------------------------------------------------------
# R6 Visual — the GEOMETRY lens (IS the Phase-D2 vision judge)
# ---------------------------------------------------------------------------

def pack_geometry(insp: "vg.Inspection",
                  include: Optional[list[str]] = None) -> dict[str, Any]:
    """R6 — package the geometry crops via the Phase-D2 gate wholesale, then stamp
    the R6 reader identity and re-check the inverse seal (the instruction must tell
    the judge NOT to assume the layout is acceptable — R6's seal). Delegates to
    ``visual_gate.pack_for_vision_judge``; adds nothing to the crop selection, since
    R6 IS that judge."""
    payload = vg.pack_for_vision_judge(insp, include=include)
    payload["reader"] = "R6"
    payload["organ"] = "rasteriser"
    payload["prompt"] = payload["instruction"]
    payload["seal"] = {"denies": list(READERS["R6"].seal_denies),
                       "allows": list(READERS["R6"].seal_allows),
                       "statement": READERS["R6"].seal}
    # the inverse seal: the geometry judge must be told NOT to trust acceptability.
    payload["seal_check"] = {
        "ok": "Do NOT assume the layout is acceptable" in payload["instruction"],
        "inverse_seal": "must not be told the layout is acceptable",
    }
    return payload


def geometry_floor(insp: "vg.Inspection") -> list[dict[str, Any]]:
    """R6 — no reader-side overfull floor (retargeted scope, 2026-07-10). Overflow
    past the text block is LOG-locatable: TeX warns on every overfull box exactly
    and the mechanical panel owns that axis via ``parse_overfull_boxes`` gated by
    the ``mech.overfull_floor_pt`` dial, every round. R6 must NOT re-inspect it, so
    this floor emits nothing (the render-native pixel detector that used to feed it
    was deleted — 22/22 of its candidates were non-defects at lock). R6's every-
    round mechanical floor is the panel's log-overfull 'visual' axis; R6's own read
    is the GEOMETRY vision judge (:func:`pack_geometry`) over collisions / tiny
    labels / clipped equations / misplaced floats / crowding — the defects the log
    cannot see. The log corroboration remains available in
    ``insp.views['overfull_log']`` for the panel, not as an R6 finding."""
    return []


def parse_geometry_verdict(raw: str, strict: bool = False) -> "vg.VisionVerdict":
    """Parse R6's vision verdict via the Phase-D2 parser (kinds already route to
    ``document``), stamped R6. Malformed → empty, never a crash. Returns a
    :class:`visual_gate.VisionVerdict` (a ``list`` subclass) so the out-of-scope
    drop count (``dropped_by_scope`` / ``dropped_kinds``) is preserved end-to-end at
    the R6 path, not lost when the findings are re-stamped (F2 observability)."""
    v = vg.parse_vision_verdict(raw, strict=strict)
    return vg.VisionVerdict(
        ({**f, "reader": "R6"} for f in v),
        dropped_by_scope=getattr(v, "dropped_by_scope", 0),
        dropped_kinds=getattr(v, "dropped_kinds", {}),
    )
