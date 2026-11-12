"""The retrieval-grounded substrate of the final voice wash (Phase I2).

``voice_descent``'s standing law: *a description of a generator does not
generate.* The last prose wash therefore may not be fenced by a lexical voice
PROFILE — it must write FROM the author's REAL prose. This module builds the
``RETRIEVED-EXEMPLARS`` channel the weld fences when ``voice_on=True``:

  * split the NEUTRAL welded draft into its ``% <sid>-pN`` paragraph units,
    reusing the canonical marker parser (``projection_viewer.parse_paragraphs``)
    so the wash reads paragraphs exactly as the viewer and the ledger do — a
    MERGE groups adjacent markers into one unit, a SPLIT repeats a marker;
  * for each unit, embed its (LaTeX-stripped) prose intent and pull the k nearest
    AUTHORED passages from the sealed bge-small store
    (``voice_corpus_ingest.nearest_authored_passage``), PER PASSAGE, DEDUPED
    across the whole document (the ``used``-set → next-nearest on a collision,
    voice_descent rule 3);
  * fence those exemplars per paragraph, keyed by the paragraph's marker(s), so
    the welder writes each paragraph FROM his own nearest prose at the moment of
    generation.

FAIL LOUD, NEVER spec-driven. The sealed store raises ``SystemExit`` when it is
unavailable (inherited from ``nearest_authored_passage`` / ``load_store``); this
module lets that propagate. The weld MUST treat it as *ship neutral or error* —
the profile-only "sound like him" pass is the named-failure embryo and is refused
(``scripts/voice_retrieve.py`` refuses the same fallback).

Contamination boundary (PIPELINE_GUIDE §4, B.5): the retrieved passages are his
real prose, and they are permitted ONLY in this ephemeral per-passage retrieval
fence — never pasted into a canon node, a brief, or any durable prompt. The
sealed vectors live tracked under ``corpus_stores/``; only this transient channel
carries the text, and only into the one weld it grounds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from laplace.manuscript import projection_viewer as _pv
from laplace.engine import voice_corpus_ingest as _vci


def paragraph_units(sid: str, text: str) -> list[dict[str, Any]]:
    """The ``% <sid>-pN`` paragraph units of one welded fragment.

    Each unit carries its joined ``spec_ids`` (a MERGE joins several; a SPLIT
    repeats one) and the LaTeX-stripped prose that is the retrieval query span —
    stripped so cosine sees his prose, not markup, symmetric with how the store
    was built. Empty when the fragment carries no paragraph markers (older or
    non-staged tex): the marker contract is load-bearing, and its absence is a
    fail-loud condition upstream, never a silent per-section degrade.
    """
    lines = text.splitlines()
    units: list[dict[str, Any]] = []
    for span in _pv.parse_paragraphs(text):
        body = "\n".join(lines[span["start_line"] - 1: span["end_line"]])
        query = " ".join(_vci.strip_latex(body).split())
        if not query:
            continue
        units.append({
            "section": span.get("section") or sid,
            "spec_id": span["spec_id"],
            "markers": span["spec_ids"],
            "query": query,
        })
    return units


def _exemplar(hit: dict[str, Any]) -> dict[str, Any]:
    """One fenced exemplar: provenance + cosine + his prose (transient fence only)."""
    loc = f"{hit['slug']}/{hit['file']} P{hit['paragraph_start']}"
    if hit.get("paragraph_end") != hit.get("paragraph_start"):
        loc += f"-P{hit['paragraph_end']}"
    return {"id": hit["passage_id"], "source": loc,
            "cos": round(float(hit["cos"]), 3), "text": hit["text"]}


def _summarise(channel: list[dict[str, Any]]) -> dict[str, Any]:
    cos = [e["cos"] for u in channel for e in u["exemplars"]]
    return {
        "paragraphs": len(channel),
        "paragraphs_with_exemplars": sum(1 for u in channel if u["exemplars"]),
        "exemplars_total": len(cos),
        "distinct_exemplars": len({e["id"] for u in channel for e in u["exemplars"]}),
        "cos_min": round(min(cos), 3) if cos else None,
        "cos_mean": round(sum(cos) / len(cos), 3) if cos else None,
        "cos_max": round(max(cos), 3) if cos else None,
    }


def build_channel(
    fragments: dict[str, str],
    order: list[str],
    *,
    k: int = 3,
    cache_root: Path | str | None = None,
    backend: Any | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The ``RETRIEVED-EXEMPLARS`` channel: one record per ``% <sid>-pN`` paragraph
    of the neutral draft, each fencing its k nearest AUTHORED passages, deduped
    PER SECTION (used-set → next-nearest on collision; the set resets at each
    section boundary — his ruling 2026-07-09: coverage over global variety, so
    every paragraph stays exemplar-grounded and reuse happens only across
    sections, where it does not read as repetition).

    Returns ``(channel, summary)`` where ``channel`` is a document-ordered list of
    ``{section, spec_id, markers, exemplars:[{id, source, cos, text}]}``.

    Raises ``SystemExit`` if the sealed store or the embedding backend is
    unavailable — the fail-loud contract. The caller MUST treat that as *ship
    neutral or error*, NEVER a spec-driven pass.
    """
    # load the sealed store ONCE; the per-paragraph queries reuse it (no N reloads)
    store = (_vci.load_store(cache_root) if cache_root is not None
             else _vci.load_store())
    if backend is None:
        from laplace.representation.embed_router import get_backend
        backend = get_backend()
    if backend is None:
        raise SystemExit("voice_retrieval: no embedding backend for the wash query.")

    units: list[dict[str, Any]] = []
    for sid in order:
        text = fragments.get(sid)
        if text:
            units.extend(paragraph_units(sid, text))

    channel: list[dict[str, Any]] = []
    used: set[str] = set()
    section: str | None = None
    for u in units:
        if u["section"] != section:
            # global dedup drained the 260-passage store over the first ~87
            # paragraphs and left the tail ungrounded — the weakest state
            used.clear()
            section = u["section"]
        hits = _vci.nearest_authored_passage(
            u["query"], k, backend=backend, store=store, exclude=used)
        used.update(h["passage_id"] for h in hits)
        channel.append({
            "section": u["section"],
            "spec_id": u["spec_id"],
            "markers": u["markers"],
            "exemplars": [_exemplar(h) for h in hits],
        })
    return channel, _summarise(channel)


#: the sidecar filename the wash's retrieved substrate is banked under (a leading
#: underscore keeps it out of the per-section decision sidecar namespace it shares
#: a directory with).
SIDECAR_NAME = "_voice_retrieval.json"


def write_channel_sidecar(path: Path | str, channel: list[dict[str, Any]],
                          summary: dict[str, Any]) -> Path:
    """PERSIST the ``RETRIEVED-EXEMPLARS`` channel + its summary to a JSON sidecar.

    The wash's generative substrate (the author's own prose, retrieved per
    paragraph) was previously derived into the weld PROMPT and thrown away — an
    ephemeral artefact with no on-disk trace, unlike its siblings (the weld
    decision sidecars, the reader verdict files, the adjudicate ``verdicts.json``).
    This file-backs it: ``{summary, channel}`` written to ``path``, so a run's
    exemplar grounding is an auditable object the author can inspect. Returns the
    written path. (This is a durable AUDIT sidecar of transient retrieval provenance
    — the exemplar TEXT it carries is his real prose and must not be re-pasted into
    a canon node or a durable prompt; PIPELINE_GUIDE §4 B.5.)"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"summary": summary, "channel": channel},
                            ensure_ascii=False, indent=1), encoding="utf-8")
    return p
