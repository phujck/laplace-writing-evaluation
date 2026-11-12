"""Pure read model for the Aisthesis Talk work surface.

The projection keeps the historical talk pipeline intact: primitives become a
motivated spine, the spine becomes a storyboard, governed assets become a deck,
and the rendered deck is checked, rehearsed and exported.  A deck is always a
projection of its beat spine.  Direct slide editing never becomes a second source
of truth.

This module reads source files only when :func:`read` is called.  It performs no
write, build, render, publication or authority action.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA = "laplace.aisthesis-talk-work/1"
BEAT_SCHEMA = "laplace.aisthesis-talk-beat/1"
_STATES = frozenset({"COMPLETE", "UNKNOWN", "REFUSED"})


def _canon(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def _handle(kind: str, value: Any) -> str:
    return f"{kind}:sha256:{hashlib.sha256(_canon(value)).hexdigest()}"


def _words(value: Any) -> str:
    return " ".join(str(value or "").split())


def _evidence_state(value: Mapping[str, Any] | None) -> tuple[str, str]:
    if value is None:
        return "UNKNOWN", "the canonical producer has not been joined"
    if not isinstance(value, Mapping):
        return "REFUSED", "the producer returned a malformed non-object value"
    explicit = _words(value.get("state") or value.get("status")).upper().replace(" ", "_")
    if value.get("error") or value.get("ok") is False:
        return "REFUSED", _words(value.get("error") or value.get("reason") or "producer refused")
    if explicit in _STATES:
        return explicit, _words(value.get("reason")) or "typed by the canonical producer"
    if not value:
        return "UNKNOWN", "the producer returned no affirmative evidence"
    return "COMPLETE", _words(value.get("reason")) or "joined from canonical read evidence"


def _omission(
    ident: str,
    label: str,
    *,
    cause: str,
    continuation: str,
    count: int = 1,
) -> dict[str, Any]:
    return {
        "id": ident,
        "semantic_anchor": f"talk:omission:{ident}",
        "label": label,
        "cause": cause,
        "count": count,
        "continuation": continuation,
    }


def _primitive(
    ident: str,
    label: str,
    value: Any,
    *,
    source: str,
    continuation: str,
) -> dict[str, Any]:
    text = _words(value)
    return {
        "id": ident,
        "semantic_anchor": f"talk:primitive:{ident}",
        "label": label,
        "value": text,
        "state": "COMPLETE" if text else "UNKNOWN",
        "reason": "declared in the talk primitives" if text else "the primitive is not settled",
        "source": source,
        "continuation": continuation,
    }


def _normalise_beat(row: Mapping[str, Any], index: int) -> dict[str, Any]:
    ident = _words(row.get("id")) or f"beat-{index + 1}"
    title = _words(row.get("title")) or f"Beat {index + 1}"
    motivation = _words(row.get("motivation") or row.get("intent"))
    claim = _words(row.get("claim") or row.get("message"))
    origin = _words(row.get("origin") or row.get("source"))
    visual = _words(row.get("visual") or row.get("figure") or row.get("equation"))
    state = "COMPLETE" if motivation and claim and origin else "UNKNOWN"
    reason = (
        "motivation, claim and source origin are present"
        if state == "COMPLETE"
        else "the beat lacks motivation, claim or source origin"
    )
    beat = {
        "schema_version": BEAT_SCHEMA,
        "id": ident,
        "semantic_anchor": f"talk:beat:{ident}",
        "title": title,
        "motivation": motivation,
        "claim": claim,
        "origin": origin,
        "visual": visual,
        "state": state,
        "reason": reason,
        "order": index,
        "citations": [_words(item) for item in row.get("citations") or [] if _words(item)],
        "assets": [dict(item) for item in row.get("assets") or [] if isinstance(item, Mapping)],
        "continuation": _words(row.get("continuation")) or f"talk://beat/{ident}",
    }
    beat["beat_handle"] = _handle("talk-beat", beat)
    return beat


def _posture(
    ident: str,
    label: str,
    value: Mapping[str, Any] | None,
    *,
    continuation: str,
) -> dict[str, Any]:
    state, reason = _evidence_state(value)
    evidence = dict(value or {}) if isinstance(value, Mapping) else {}
    return {
        "id": ident,
        "semantic_anchor": f"talk:posture:{ident}",
        "label": label,
        "state": state,
        "reason": reason,
        "evidence": evidence,
        "continuation": continuation,
    }


def project(
    *,
    title: str = "",
    primitives: Mapping[str, Any] | None = None,
    motivated_spine: Sequence[Mapping[str, Any]] | None = None,
    generation: Mapping[str, Any] | None = None,
    ledger: Mapping[str, Any] | None = None,
    rehearsal: Mapping[str, Any] | None = None,
    export: Mapping[str, Any] | None = None,
    observation_time: str = "",
    source_currentness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one immutable talk surface from already-admitted evidence."""
    primitive_values = dict(primitives or {})
    primitive_rows = [
        _primitive(
            "source",
            "Source material",
            primitive_values.get("source"),
            source=_words(primitive_values.get("source_node")) or "talk source quarry",
            continuation="talk://primitives/source",
        ),
        _primitive(
            "audience",
            "Audience",
            primitive_values.get("audience"),
            source=_words(primitive_values.get("audience_source")) or "author ruling",
            continuation="talk://primitives/audience",
        ),
        _primitive(
            "message",
            "Message",
            primitive_values.get("message"),
            source=_words(primitive_values.get("message_source")) or "motivated spine",
            continuation="talk://primitives/message",
        ),
    ]
    beats = [
        _normalise_beat(row, index)
        for index, row in enumerate(motivated_spine or ())
        if isinstance(row, Mapping)
    ]
    if not beats:
        spine_state = "UNKNOWN"
        spine_reason = "the motivated beat spine has not been joined"
    elif any(row["state"] == "UNKNOWN" for row in beats):
        spine_state = "UNKNOWN"
        spine_reason = "one or more beats lack motivation, claim or source origin"
    else:
        spine_state = "COMPLETE"
        spine_reason = "every beat carries motivation, claim and source origin"

    postures = [
        _posture("generation", "Generate from the spine", generation, continuation="talk://generation"),
        _posture("ledger", "Rendered talk ledger", ledger, continuation="talk://ledger"),
        _posture("rehearsal", "Rehearsal cadence", rehearsal, continuation="talk://rehearsal"),
        _posture("export", "Export and listing", export, continuation="talk://export"),
    ]

    direct_slide_truth = bool((generation or {}).get("direct_slide_truth")) if isinstance(generation, Mapping) else False
    if direct_slide_truth:
        postures[0]["state"] = "REFUSED"
        postures[0]["reason"] = "direct slide truth violates governed beat regeneration"

    omissions: list[dict[str, Any]] = []
    for row in primitive_rows:
        if row["state"] != "COMPLETE":
            omissions.append(
                _omission(
                    f"primitive-{row['id']}",
                    f"{row['label']} is unsettled",
                    cause=row["state"],
                    continuation=row["continuation"],
                )
            )
    if spine_state != "COMPLETE":
        omissions.append(
            _omission(
                "motivated-spine",
                "Motivated beat context is incomplete",
                cause=spine_state,
                continuation="talk://spine",
                count=max(1, sum(row["state"] != "COMPLETE" for row in beats)),
            )
        )
    for row in postures:
        if row["state"] != "COMPLETE":
            omissions.append(
                _omission(
                    row["id"],
                    f"{row['label']} evidence is unavailable",
                    cause=row["state"],
                    continuation=row["continuation"],
                )
            )

    states = [row["state"] for row in primitive_rows] + [spine_state] + [
        row["state"] for row in postures
    ]
    overall = "REFUSED" if "REFUSED" in states else "UNKNOWN" if "UNKNOWN" in states else "COMPLETE"
    body: dict[str, Any] = {
        "schema_version": SCHEMA,
        "semantic_anchor": "work:talk",
        "title": _words(title) or "Untitled talk",
        "state": overall,
        "observation_time": observation_time,
        "source_currentness": dict(source_currentness or {}),
        "primitives": primitive_rows,
        "spine": {
            "semantic_anchor": "talk:spine",
            "label": "Motivated spine",
            "state": spine_state,
            "reason": spine_reason,
            "beats": beats,
            "beat_count": len(beats),
            "continuation": "talk://spine",
        },
        "postures": postures,
        "projection_law": {
            "source_of_truth": "primitives + motivated spine + storyboard beats",
            "deck_role": "generated projection",
            "visual_editing": "governed beat regeneration",
            "direct_slide_truth": False,
            "renderer_executes": False,
        },
        "omissions": omissions,
        "ordered_visible_handles": [row["beat_handle"] for row in beats],
        "read_only": True,
        "authority_effect": "none",
    }
    body["omitted_digest"] = _handle("talk-omissions", omissions)
    body["model_handle"] = _handle("talk-model", body)
    return body


_BEAT_RE = re.compile(r"^##\s+([^|]+)\|\s*([^|]+)\|", re.MULTILINE)


def _blueprint(path: Path) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    text = path.read_text(encoding="utf-8")
    metadata: dict[str, str] = {}
    for key in ("thesis", "frame", "title", "register"):
        match = re.search(rf"^-\s+{key}:\s*(.+)$", text, re.MULTILINE)
        if match:
            metadata[key] = _words(match.group(1))
    provenance = re.search(r"NOTE \(provenance\):\s*(.+?)(?=\n\n|\n##)", text, re.DOTALL)
    source_words = _words(provenance.group(1)) if provenance else str(path)
    matches = list(_BEAT_RE.finditer(text))
    beats: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chunk = text[match.end() : end]
        intent = re.search(r"^intent:\s*(.+)$", chunk, re.MULTILINE)
        claims = re.findall(r"^-\s+claim:\s*(.+?)(?:\s+\||$)", chunk, re.MULTILINE)
        figures = re.findall(r"^-\s+figure:\s*(.+)$", chunk, re.MULTILINE)
        equations = re.findall(r"^-\s+equation:\s*(.+)$", chunk, re.MULTILINE)
        citations = re.findall(r"^-\s+cite:\s*([^|\s]+)", chunk, re.MULTILINE)
        ident = _words(match.group(1)).lower().replace(" ", "_")
        beats.append(
            {
                "id": ident,
                "title": _words(match.group(2)),
                "motivation": _words(intent.group(1)) if intent else "",
                "claim": _words(claims[0]) if claims else "",
                "origin": f"{path}:{match.group(0).strip()}",
                "visual": _words((figures or equations or [""])[0]),
                "citations": citations,
                "continuation": f"source://{path}#{ident}",
            }
        )
    primitives = {
        "source": source_words,
        "source_node": str(path),
        "audience": metadata.get("audience", ""),
        "message": metadata.get("thesis", ""),
        "message_source": str(path),
    }
    return metadata.get("title", path.parent.name.replace("-", " ").title()), primitives, beats


def read(
    *,
    project_dir: Path,
    observation_time: str = "",
    source_currentness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read one historical talk quarry without executing any producer or writer."""
    root = project_dir.resolve()
    blueprint = root / "blueprint.md"
    if not blueprint.is_file():
        return project(
            title=root.name,
            observation_time=observation_time,
            source_currentness=source_currentness,
        )
    title, primitives, beats = _blueprint(blueprint)
    slides = root / "slides.md"
    has_slides = slides.is_file()
    generated = False
    if has_slides:
        head = slides.read_text(encoding="utf-8")[:1024]
        generated = "GENERATED FROM" in head.upper() and "SPINE" in head.upper()
    generation: dict[str, Any] = {
        "state": "COMPLETE" if generated else "UNKNOWN",
        "reason": (
            "deck carries a generated-from-spine header"
            if generated
            else "a deck exists, but no governed regeneration receipt is present"
        ),
        "deck_present": has_slides,
        "generated_from_spine": generated,
        "direct_slide_truth": False,
        "source": str(slides),
    }
    blind_read = root / "BLIND_READ.md"
    ledger: dict[str, Any] = {
        "state": "UNKNOWN",
        "reason": "no rendered talk-ledger receipt is present",
        "blind_read_present": blind_read.is_file(),
        "voice": "UNKNOWN",
        "applets": "UNKNOWN",
        "render": "UNKNOWN",
    }
    rehearsal: dict[str, Any] = {
        "state": "UNKNOWN",
        "reason": "no timed rehearsal or speaker-cadence receipt is present",
        "notes_channel": "UNKNOWN",
    }
    export_path = root / "deck.pdf"
    exported: dict[str, Any] = {
        "state": "COMPLETE" if export_path.is_file() else "UNKNOWN",
        "reason": "exported deck is present" if export_path.is_file() else "no exported deck is present",
        "pdf_present": export_path.is_file(),
        "listed": "UNKNOWN",
    }
    return project(
        title=title,
        primitives=primitives,
        motivated_spine=beats,
        generation=generation,
        ledger=ledger,
        rehearsal=rehearsal,
        export=exported,
        observation_time=observation_time,
        source_currentness=source_currentness,
    )


__all__ = ["BEAT_SCHEMA", "SCHEMA", "project", "read"]
