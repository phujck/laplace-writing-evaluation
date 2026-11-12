"""collaborator_lens.py - the g0 substrate of the collaborator corpus (the relational map).

The conjugate of ``concept_lens`` for people instead of papers, on the SAME atoms-g0 floor (his rule): a
COLLABORATOR is a g1+ cluster (the person file), their distilled CONTRIBUTIONS are the g0 atoms beneath.
The person files are materialised by ``scripts/ingest_collaborators.py`` (real files the keeper grades via
``dir_parent``); this module materialises the virtual g0 contribution-atom leaves (``<person>::<atom>``,
routed up to the person by the generic ``concept_lens.atom_parent``) and their structural coupling.

An atom's reach referent is its PERSON (``inperson::``), so two contributions couple by STRUCTURE (same
person), never by their shared physics vocabulary - the same keyword-pollution fix the concept atoms use.
The CONFIDENCE the swarm graded each contribution is carried on the leaf (his spectral-radius insight): the
continuous weight a future ``effective spectral radius`` (F1) will use to set how readily it surfaces;
``low`` is the conjectural grit. No LLM here - deterministic materialise of the committed distillates.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from laplace.engine.concept_lens import ATOM_SEP, _tokens

_PEOPLE = "collaborator_corpus/people/"
_DISTILL = "collaborator_corpus/_distillates"
_VOICE = "collaborator_corpus/_voice"      # scientific-voice folds (from the PAPERS, public bib)
_ESSENCE_CAP = 320
_STOP = {"and", "the", "of", "for", "in", "to", "a", "via", "hhg", "ert", "cif"}


def _stem(t: str) -> str:
    return t[:-1] if len(t) > 4 and t.endswith("s") else t   # light plural fold (superoscillations->...tion)


def _slug_toks(slug: str) -> set[str]:
    return {_stem(t) for t in re.split(r"[^a-z0-9]+", slug.lower()) if len(t) > 2 and t not in _STOP}


def _lens_slugs(repo_root: Path, kind: str) -> dict[str, set[str]]:
    d = repo_root / "concept_corpus" / kind
    return {f"concept_corpus/{kind}/{f.stem}.md": _slug_toks(f.stem)
            for f in sorted(d.glob("*.md"))} if d.is_dir() else {}


def _best_match(tokens: set[str], targets: dict[str, set[str]], min_overlap: int = 2) -> str | None:
    best, score = None, min_overlap - 1
    for nid, toks in targets.items():
        s = len(tokens & toks)
        if s > score:
            best, score = nid, s
    return best


def cross_corpus_wires(repo_root: Path | str) -> dict[str, set[str]]:
    """``person node id -> the lens nodes (themes + co-authored papers) they faithfully wire to.`` Matched
    from each collaborator's distilled shared-themes (-> lens themes) and contribution-atom names (-> the
    lens papers they co-authored), by token overlap against the REAL lens slugs (>=2, never forced). The
    one source of truth for the cross-corpus link, used by both the materialiser (the ``[[..]]`` wires in
    the person file) and the coupling (``collaborator_edge_index``)."""
    root = Path(repo_root)
    themes, papers = _lens_slugs(root, "themes"), _lens_slugs(root, "atoms")
    out: dict[str, set[str]] = {}
    for rec in _distillates(root):
        person = f"{_PEOPLE}{rec.get('_key','')}.md"
        wires: set[str] = set()
        for th in rec.get("shared_themes", []):
            m = _best_match(_slug_toks(th), themes)
            if m:
                wires.add(m)
        for a in rec.get("contribution_atoms", []):
            m = _best_match(_slug_toks(a.get("name", "")), papers)
            if m:
                wires.add(m)
        if wires:
            out[person] = wires
    return out


def _distillates(repo_root: Path | str) -> list[dict[str, Any]]:
    d = Path(repo_root) / _DISTILL
    out: list[dict[str, Any]] = []
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            out.append(json.loads(f.read_text(encoding="utf-8")))
    return out


def voice_records(repo_root: Path | str) -> list[dict[str, Any]]:
    """The scientific-voice folds (``_voice/<key>.json``, one per collaborator): how they THINK in
    the literature, distilled from their public papers (titles+abstracts) by the observe->fold->
    adjudicate swarm (``scripts/wf_voice_from_papers.mjs``). The conjugate of the chat voice: the
    soul holds how they speak to Gerard; this holds how they argue in print. Public bib - committed."""
    d = Path(repo_root) / _VOICE
    out: list[dict[str, Any]] = []
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            if f.name.startswith("_"):
                continue
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return out


def collaborator_leaves(repo_root: Path | str) -> dict[str, dict[str, Any]]:
    """The g0 contribution-atoms beneath each collaborator (one node per distilled contribution). Virtual
    nodes (NOT files): the person file holds them as content, a reconstruction bottoms at the statement.
    Id is ``<person-file>::<atom-name>`` so ``atom_parent`` routes it up to its person cluster. Carries the
    swarm's confidence grade on the leaf (the weight for the spectral-radius surfacing; ``low`` = grit)."""
    out: dict[str, dict[str, Any]] = {}
    for rec in _distillates(repo_root):
        key = rec.get("_key", "")
        person = f"{_PEOPLE}{key}.md"
        seen: set[str] = set()
        for a in rec.get("contribution_atoms", []):
            name = (a.get("name") or "").strip()
            if not name:
                continue
            aid = f"{person}{ATOM_SEP}{name}"
            if aid in seen:
                continue
            seen.add(aid)
            kind = a.get("kind", "concept")
            stmt = (a.get("statement") or "").strip()
            conf = a.get("confidence", "medium")
            out[aid] = {"kind": f"collab-{kind}", "essence": f"{kind}: {stmt}"[:_ESSENCE_CAP],
                        "keywords": _tokens(f"{name} {stmt}")[:14], "sealed": False,
                        "confidence": conf, "conjectural": conf == "low"}
    # the scientific-voice atoms: same floor, same routing, ``voice-`` prefixed so a person's
    # voice and their contributions stay distinguishable on the leaf (kind voice-move/style/...)
    for rec in voice_records(repo_root):
        key = rec.get("_key") or rec.get("key", "")
        person = f"{_PEOPLE}{key}.md"
        seen = set()
        for v in rec.get("voice_items", []):
            name = (v.get("name") or "").strip()
            if not name:
                continue
            aid = f"{person}{ATOM_SEP}voice-{name}"
            if aid in seen:
                continue
            seen.add(aid)
            kind = v.get("kind", "move")
            stmt = (v.get("statement") or "").strip()
            conf = v.get("confidence", "medium")
            out[aid] = {"kind": f"voice-{kind}", "essence": f"voice ({kind}): {stmt}"[:_ESSENCE_CAP],
                        "keywords": _tokens(f"{name} {stmt}")[:14], "sealed": False,
                        "confidence": conf, "conjectural": conf == "low",
                        "works": (v.get("works") or [])[:12]}
    return out


def collaborator_edge_index(repo_root: Path | str) -> dict[str, list[str]]:
    """The collaborator atoms' structural referents for ``build_reach``: each contribution atom -> its
    PERSON (``inperson::`` token), so contributions couple by the person they belong to, NOT by their bag
    of physics keywords (the same containment fix the concept atoms use). The faithful cross-corpus
    coupling to the lens lives in the person FILE's ``[[concept_corpus/...]]`` wires (picked up by the
    self-shard edges) AND minted here as shared ``xcorpus::`` tokens (a directed ``[[link]]`` puts the
    target in the source's reach only, which does NOT couple - coupling needs a shared referent on both
    ends, as the conceptric does). This keeps the floor from leaking vocabulary AND couples each person to
    the lens physics they co-built."""
    idx: dict[str, list[str]] = {}
    for rec in _distillates(repo_root):
        person = f"{_PEOPLE}{rec.get('_key','')}.md"
        for a in rec.get("contribution_atoms", []):
            name = (a.get("name") or "").strip()
            if name:
                idx[f"{person}{ATOM_SEP}{name}"] = [f"inperson::{person}"]
    for rec in voice_records(repo_root):
        person = f"{_PEOPLE}{rec.get('_key') or rec.get('key','')}.md"
        for v in rec.get("voice_items", []):
            name = (v.get("name") or "").strip()
            if name:
                idx[f"{person}{ATOM_SEP}voice-{name}"] = [f"inperson::{person}"]
    for person, lens_nodes in cross_corpus_wires(repo_root).items():
        for ln in sorted(lens_nodes):
            token = f"xcorpus::{person}<->{ln}"          # undirected: shared by both ends -> real coupling
            idx.setdefault(person, []).append(token)
            idx.setdefault(ln, []).append(token)
    return idx
