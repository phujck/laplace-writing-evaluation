"""The sealed-subagent organ — R1 Cold, R4 Skimmer, R7 Feral-prose.

One harness, three lenses. Each reader meets the manuscript as a reader meets it
(the RENDERED artifact, never the substrate/spec/plan), differing only in the
**input slice** it is shown and the **lens** (the recoverables checklist) it reads
for:

    * R1 Cold    — the WHOLE rendered text; reconstruct problem/method/each-eq-role/
                   each-figure-role/evidence-boundary/conclusion.
    * R4 Skimmer — input TRUNCATED to abstract+captions+conclusion; skim-reconstruct
                   the skim-path (the body is physically absent from its input).
    * R7 Feral   — prose-only (math/environments masked); read for cadence/mannerism.

Following the Phase-D2 ``visual_gate`` pattern: this module PACKAGES the sealed read
(slice + prompt + recoverables + the SEAL) and PARSES the verdict into the standard
finding shape — it does NOT call a model. Phase F drives the actual sealed-subagent
model call at candidate-lock (the least-capable model, per ``blind_reader``'s
"worse is better"). The mechanical FLOOR (leaked-meta + define-before-use census)
runs every round and reuses the ``blind_reader`` script's primitives BY IMPORT — one
implementation of the pre-pass, shared by the CLI and the reader suite.

The seal is structural: a slicer reads only ``_gather_manuscript_text`` (the rendered
manuscript, comment-stripped — the ``%<sid>-pN`` provenance thread is already gone),
so the construction intention cannot enter. :func:`seal_holds` re-checks the packaged
payload against a sentinel list, so a regression that let a spec leak is caught.
"""

from __future__ import annotations
from laplace.core.checkout import package_root

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any, Optional

from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline.readers.roster import READERS, reader_finding


# ---------------------------------------------------------------------------
# Reuse the blind_reader mechanical floor BY IMPORT (not reimplemented)
# ---------------------------------------------------------------------------

_BLIND_READ_PATH = (package_root()
                    / "canon/skills/blind_reader/scripts/blind_read.py")
_blind_mod: Optional[ModuleType] = None


def _blind() -> ModuleType:
    """Load the ``blind_read.py`` skill script as a module (cached). It lives under
    ``canon/skills/.../scripts`` — not a normal import path — so it is loaded by
    absolute location, computed relative to the ``laplace`` package so it survives a
    move of the repo. Its functions (``mask_regions``, ``find_leaked_meta``,
    ``census_terms``) are the single source of the mechanical pre-pass."""
    global _blind_mod
    if _blind_mod is None:
        spec = importlib.util.spec_from_file_location(
            "laplace_blind_read", _BLIND_READ_PATH)
        if spec is None or spec.loader is None:      # pragma: no cover
            raise RuntimeError(f"cannot load blind_read from {_BLIND_READ_PATH}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _blind_mod = mod
    return _blind_mod


# ---------------------------------------------------------------------------
# The seal — what the reader must NEVER be shown (the construction intention)
# ---------------------------------------------------------------------------
#
# Sentinels of the spec/plan/policy/narrative packet. A slicer that only reads the
# rendered manuscript cannot admit these; :func:`seal_holds` proves it did not.
SPEC_SENTINELS: tuple[str, ...] = (
    "POLICY", "OBJECT channel", "builder_contract", "narrative spec",
    "projection-plan", "projection_spec", "blueprint", "storyboard",
    "reading_order", "set-spine", "set-meta", "dispatch", "worklist",
    "epistemic_labels", "type_tag", "%<sid>", "sid-p", "we are explicit about what is new",
)


def seal_holds(payload: dict[str, Any]) -> dict[str, Any]:
    """Assert the sealed payload leaks no construction intention. Scans the sealed
    input AND the prompt for any :data:`SPEC_SENTINELS`. Returns
    ``{ok, leaks}`` — ``leaks`` names each sentinel found and where. This is the
    acceptance surface for "the seal strips spec/intention" (builder ≠ judge: the
    builder proves the plumbing, not the read quality)."""
    hay_input = payload.get("sealed_input", "") or ""
    hay_prompt = payload.get("prompt", "") or ""
    leaks: list[dict[str, str]] = []
    for s in SPEC_SENTINELS:
        # a rendered manuscript may legitimately contain a lone common word; the
        # sentinels are chosen to be construction-only tokens, matched literally.
        if s in hay_prompt:
            leaks.append({"sentinel": s, "where": "prompt"})
        if s in hay_input:
            leaks.append({"sentinel": s, "where": "sealed_input"})
    return {"ok": not leaks, "leaks": leaks}


# ---------------------------------------------------------------------------
# Input slicers — the correct sealed slice per lens
# ---------------------------------------------------------------------------

_ABSTRACT_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL)
_ABSTRACT_CMD_RE = re.compile(r"\\abstract\{((?:[^{}]|\{[^{}]*\})*)\}", re.DOTALL)
_CAPTION_RE = re.compile(r"\\caption\{((?:[^{}]|\{[^{}]*\})*)\}", re.DOTALL)
_SECTION_RE = re.compile(r"\\(sub)?section\*?\{([^}]+)\}")
_CONCL_TITLE = re.compile(r"\b(conclusion|closing|summary|outlook|discussion)\b", re.I)


def full_slice(target: str | Path) -> str:
    """R1 — the whole rendered text, as a reader meets it (flattened along the
    ``\\input`` tree, comments stripped). No truncation, no masking."""
    return _gather_manuscript_text(target)


def prose_slice(target: str | Path) -> str:
    """R7 — prose only. Mask math, environments, comments (reusing the blind_reader
    masker, so a symbol like ``$Z_\\tau$`` is never read as prose), then collapse the
    blanked runs so the cadence reader sees sentences, not a lattice of spaces."""
    full = _gather_manuscript_text(target)
    masked = _blind().mask_regions(full, ".tex")
    # collapse the blanked runs; keep paragraph breaks (double newline) so cadence
    # is read within paragraphs, not across the whole document as one run-on.
    paras = re.split(r"\n\s*\n", masked)
    out = []
    for p in paras:
        collapsed = re.sub(r"[ \t]+", " ", p.replace("\n", " ")).strip()
        if len(collapsed.split()) >= 5:              # drop float-only / stub blocks
            out.append(collapsed)
    return "\n\n".join(out)


def skim_slice(target: str | Path) -> str:
    """R4 — the truncated skim-path: the abstract, every figure/table caption, and
    the conclusion section, in that order. The BODY is physically excluded — the
    reader cannot resolve a skim overclaim against the body it never sees, which is
    exactly the bandwidth a skimming referee has. Returns a labelled slice so the
    reader knows which region each block came from."""
    full = _gather_manuscript_text(target)
    parts: list[str] = []

    m = _ABSTRACT_RE.search(full) or _ABSTRACT_CMD_RE.search(full)
    parts.append("=== ABSTRACT ===\n" + (m.group(1).strip() if m else "(no abstract environment present)"))

    caps = [c.group(1).strip() for c in _CAPTION_RE.finditer(full)]
    if caps:
        parts.append("=== CAPTIONS ===\n" + "\n---\n".join(caps))

    # the conclusion section span: from its heading to the next section (or end).
    marks = [(mm.start(), mm.group(2)) for mm in _SECTION_RE.finditer(full)]
    concl = ""
    for i, (start, name) in enumerate(marks):
        if _CONCL_TITLE.search(name or ""):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(full)
            concl = full[start:end].strip()
            break
    parts.append("=== CONCLUSION ===\n" + (concl or "(no conclusion section found)"))
    return "\n\n".join(parts)


_SLICERS = {"R1": full_slice, "R4": skim_slice, "R7": prose_slice}


def slice_for(reader_id: str, target: str | Path) -> str:
    """The sealed input slice for a sealed-subagent reader (R1/R4/R7)."""
    if reader_id not in _SLICERS:
        raise KeyError(f"{reader_id} is not a sealed-subagent reader "
                       f"(have {sorted(_SLICERS)})")
    return _SLICERS[reader_id](target)


# ---------------------------------------------------------------------------
# The lens — the recoverables checklist + the instruction, per reader
# ---------------------------------------------------------------------------

_FLOOR_REFEREE = (
    "You are a referee meeting this work COLD. You have NOT been briefed on the "
    "authors' intention, plan, or narrative — only the page in front of you. Do "
    "NOT try to orient, look up the project, or resolve a term from your own "
    "knowledge: the test is what THIS PAGE grounds, not what you happen to know. "
    "If a term is used before the page defines or cites it, that is a finding, "
    "however obvious it reads to you. Report confusion, not approval.")

_RECOVERABLES: dict[str, list[str]] = {
    "R1": [
        "the PROBLEM the paper attacks (one line, from the page)",
        "the METHOD, in one line",
        "the role of EACH numbered equation (why the reader is shown it)",
        "the role of EACH figure (what one thing it is for)",
        "the EVIDENCE BOUNDARY — what is proven vs measured vs asserted",
        "the CONCLUSION — the single claim the paper lands",
    ],
    "R4": [
        "the ONE-LINE contribution, from the abstract alone",
        "what each figure shows, from its caption alone",
        "whether the CONCLUSION answers the promise the ABSTRACT made",
        "any place the abstract/headings/conclusion OVERCLAIM beyond what a "
        "skimmer could verify",
        "any abstract sentence that narrates the paper's own STRUCTURE rather "
        "than stating a result",
    ],
    "R7": [
        "sentence-movement uniformity (do sentences all run the same length/shape?)",
        "list-of-three tics and other rhetorical templates repeated mechanically",
        "hedging scaffold ('it is worth noting', 'importantly', 'note that')",
        "a phrase or transition MANNERISM that recurs unnaturally",
        "any passage that reads as GENERATED rather than authored",
    ],
}

_INSTRUCTIONS: dict[str, str] = {
    "R1": (_FLOOR_REFEREE + " Read the WHOLE artifact below and, for each item in "
           "the recoverables checklist, state whether you could recover it FROM THE "
           "PAGE and quote where. Where you could not, that is a finding."),
    "R4": (_FLOOR_REFEREE + " You are shown ONLY the skim-path — the abstract, the "
           "captions, and the conclusion. The body is deliberately withheld: judge "
           "the paper as a referee who only skims. For each recoverables item, "
           "report what the skim-path does and does not deliver."),
    "R7": ("You are a reader with an ear for PROSE. You are shown the prose only "
           "(math and floats removed) and you have NOT been told the house voice or "
           "any style rule — do not check the prose against a profile, FEEL it. "
           "Report every place the writing reads as machine-generated: uniform "
           "cadence, templated rhetoric, hedging scaffold, a recurring mannerism."),
}


def _allowed_kinds(reader_id: str) -> list[str]:
    return list(READERS[reader_id].owned_kinds)


# ---------------------------------------------------------------------------
# The section-anchor stamp — the reader pour path routes a finding by section
# ---------------------------------------------------------------------------

_WHERE_SECTION_RE = re.compile(r"^\s*(N(?:A\d+|\d+))\b")


def section_from_where(where: str) -> str | None:
    """The section a sealed reader's finding is anchored to, from the LEADING
    location token in its free-text ``where``. Sealed readers meet the rendered
    manuscript and name where they are as they read it ('N3-p16 / ...', 'N4-p10: ...'),
    so a leading ``N<k>`` / ``NA<k>`` token IS the section stamp — this is the anchor
    the plain reader pour applies (:func:`ledger.pour_finding`).

    Deliberately conservative: ONLY a leading section token is trusted. A mid-string
    ``N<k>`` is not (e.g. a finding IN the introduction that quotes
    ``Sec.~\\ref{sec:N2}`` is anchored to the intro, NOT to N2 — the leading-token
    rule refuses to mis-anchor it, and the pour then requires the reader to supply the
    section explicitly rather than guess). Unlocatable → ``None`` (the pour refuses)."""
    m = _WHERE_SECTION_RE.match(where or "")
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# 1. The mechanical floor — every round, no model
# ---------------------------------------------------------------------------

def mechanical_floor(reader_id: str, target: str | Path,
                     terms: Optional[list[str]] = None, window: int = 0
                     ) -> list[dict[str, Any]]:
    """The cheap high-precision pre-pass that runs EVERY fixer round for a
    sealed-subagent reader — the deterministic floor under the oracle. Reuses the
    ``blind_reader`` primitives on the reader's OWN input slice:

      * R1 — leaked-meta on the whole text + a define-before-use census (when a
        glossary of terms is supplied),
      * R4 — leaked-meta on the skim-path (an abstract that leaks the roadmap fires
        here before the model is ever spent),
      * R7 — leaked-meta on the prose slice.

    Findings keep the blind_read floor kinds (``leaked-meta`` / ``undefined-term`` /
    ``use-before-define`` — reused, owned by the ``meta_leak`` gate) but are stamped
    with the ``reader`` so Phase F attributes the round-floor to the right reader."""
    b = _blind()
    text = slice_for(reader_id, target)
    # R7's prose slice is already masked+collapsed → treat as plain prose (.txt),
    # so the floor does not re-mask readable prose to spaces. The census only
    # applies to R1 (a define-before-use glossary is a whole-text concept).
    ext = ".tex" if reader_id in ("R1", "R4") else ".txt"
    census = terms if reader_id == "R1" else None
    flags = b.reader_floor(text, ext, census, window)
    out: list[dict[str, Any]] = []
    for fl in flags:
        kind = fl.get("kind", "leaked-meta")
        where = f"line {fl.get('line', '?')}"
        out.append({**reader_finding(reader_id, where, fl.get("message", ""),
                                     None, kind), "floor": True})
    return out


# ---------------------------------------------------------------------------
# 2. Package the sealed read (for Phase F to drive the model)
# ---------------------------------------------------------------------------

def pack_for_sealed_read(reader_id: str, target: str | Path,
                         max_input_chars: int = 120_000) -> dict[str, Any]:
    """Package a sealed read: the input slice, the built prompt (referee floor +
    recoverables + the finding schema), the allowed kinds, and the seal state.
    Phase F supplies the (least-capable) model and calls
    :func:`parse_sealed_verdict` on the reply. This module never calls a model.

    ``max_input_chars`` caps a very long artifact (R1 on a whole manuscript) so a
    single read stays within a small model's window; the cap is recorded in the
    payload (``truncated``) so a truncated read is never mistaken for a full one —
    silence never reads as pass."""
    if reader_id not in _SLICERS:
        raise KeyError(f"{reader_id} is not a sealed-subagent reader")
    sliced = slice_for(reader_id, target)
    truncated = len(sliced) > max_input_chars
    sealed_input = sliced[:max_input_chars]
    recoverables = _RECOVERABLES[reader_id]
    checklist = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(recoverables))
    prompt = (
        f"{_INSTRUCTIONS[reader_id]}\n\n"
        f"RECOVERABLES CHECKLIST:\n{checklist}\n\n"
        "Return ONLY JSON: a list of findings, each "
        '{"where": "<section/line>", "issue": "<what you could not follow / the '
        'defect>", "fix": "<smallest change>", "kind": "<one of the allowed '
        f'kinds>"}}. Allowed kinds: {_allowed_kinds(reader_id)}. Empty list if the '
        "artifact fully passes this lens.\n\n"
        "=== THE ARTIFACT (read only this) ===\n"
        f"{sealed_input}"
    )
    payload = {
        "reader": reader_id,
        "organ": "sealed_subagent",
        "model_hint": "least-capable (worse is better — a narrower knowledge base "
                      "is the more faithful cold-reader proxy)",
        "instruction": _INSTRUCTIONS[reader_id],
        "recoverables": recoverables,
        "allowed_kinds": _allowed_kinds(reader_id),
        "finding_schema": ["where", "issue", "fix", "kind"],
        "seal": {"denies": list(READERS[reader_id].seal_denies),
                 "allows": list(READERS[reader_id].seal_allows),
                 "statement": READERS[reader_id].seal},
        "sealed_input": sealed_input,
        "prompt": prompt,
        "truncated": truncated,
    }
    payload["seal_check"] = seal_holds(payload)
    return payload


def to_content_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn a sealed-read payload into Anthropic-style content blocks (one text
    block — the sealed prompt). Standalone: no SDK import. Symmetry with
    ``visual_gate.to_content_blocks`` so Phase F drives both organs the same way."""
    return [{"type": "text", "text": payload["prompt"]}]


# ---------------------------------------------------------------------------
# 3. Parse the verdict
# ---------------------------------------------------------------------------

def _coerce_json(raw: str) -> Any:
    """Pull a JSON body out of a possibly fenced / prosey reply (shared shape with
    ``visual_gate._coerce_json``)."""
    import json
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("[", "]"), ("{", "}")):
        i, j = raw.find(opener), raw.rfind(closer)
        if 0 <= i < j:
            try:
                return json.loads(raw[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


def parse_sealed_verdict(reader_id: str, raw: str, strict: bool = False
                         ) -> list[dict[str, Any]]:
    """Parse a sealed reader's reply into findings in the standard shape, stamped
    with the reader and routed via the roster. Accepts a bare list,
    ``{"findings": [...]}``, or fenced JSON. An unknown/missing kind coerces to the
    reader's FIRST owned kind (still correctly routed) unless ``strict`` drops it.
    Malformed input → ``[]`` — never a crash. Tolerant by design: a weak model's
    verdict is noisy, and we would rather route a mis-kinded finding to the right
    reader than lose it."""
    data = _coerce_json(raw)
    if isinstance(data, dict):
        data = data.get("findings", data.get("verdict", []))
    if not isinstance(data, list):
        return []
    allowed = set(_allowed_kinds(reader_id))
    default_kind = _allowed_kinds(reader_id)[0] if allowed else "note"
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip()
        if kind not in allowed:
            if strict:
                continue
            kind = default_kind
        out.append(reader_finding(
            reader_id,
            str(item.get("where", "")).strip(),
            str(item.get("issue", "")).strip(),
            (str(item.get("fix", "")).strip() or None),
            kind,
            quote=(str(item.get("quote", "")).strip() or None)))
    return out
