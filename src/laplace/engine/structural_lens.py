"""structural_lens.py - the regraded PROGRAM ladder as routable, graded substrate.

The deposit step of the insert-middle loop (his 2026-06-11: "when you bank and ingest new
information, you're sharding each layer through our recursive embedder - just to make sure
all this effort isn't being wasted"). A ``*_regraded.json`` under ``collaborator_corpus/
_structural/`` is the closure-gated structural ladder of one author's corpus: generators
(the research program's top lenses) -> rungs (the confirmed mid-grades) -> papers (the
floor). This module materialises that ladder as virtual nodes the keeper grades and the
embed router folds at fold time - generator and rung nodes are AUTHORED leaves carrying
their RESPONSE-FUNCTION essences (what the node IS / what a goal arriving pulls below /
what returns upward), so they keep those essences when children attach (the authored-
coarse-node rule in ``keeper.build_tree``). No LLM here - deterministic materialise of
the committed, gate-passed artefacts; intelligence was paid at the fold.

Ids nest with ``//`` below the first ``::`` so ``structural_parent`` (checked BEFORE
``concept_lens.atom_parent`` in the keeper's parent chain) preserves the ladder:
  <file>::<gen-slug>                      the generator (authored essence)
  <file>::<gen-slug>//<rung-name>         the rung (authored essence)
  <file>::<gen-slug>//<rung>//<W-id>      the paper leaf (title + meta-goal handle)
Coupling is structural (``inrung::`` / ``ingen::`` referents), never bag-of-physics-words -
the same keyword-pollution fix the concept and collaborator atoms use.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from laplace.engine.concept_lens import _tokens

_STRUCT = "collaborator_corpus/_structural"
_STRUCT_DIRS = (                       # every home a regraded ladder may live in (committed ones travel)
    "collaborator_corpus/_structural",  # the collaborators' corpora
    "engine_corpus/_structural",        # the engine's own operations lens (the mechanised workings)
    "synthetics_corpus/_structural",    # the physics_paper_orchestra synthetic paper-projects (the synthetics lens)
    "archive/self_record/_structural",  # the self-record (local until his oracle eye passes the upfold)
)
_RAW = "collaborator_corpus/_raw"
_PEOPLE = "collaborator_corpus/people/"
NEST_SEP = "//"


def _slug(label: str, cap: int = 5) -> str:
    toks = [t for t in re.split(r"[^a-z0-9]+", label.lower()) if t][:cap]
    return "-".join(toks)


def _records(repo_root: Path | str) -> list[tuple[str, dict[str, Any]]]:
    """``(relpath, record)`` for each regraded ladder across every ``_structural`` home."""
    out: list[tuple[str, dict[str, Any]]] = []
    for rel in _STRUCT_DIRS:
        d = Path(repo_root) / rel
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*_regraded.json")):
            try:
                out.append((f"{rel}/{f.name}", json.loads(f.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError):
                continue
    return out


def _titles(repo_root: Path | str, key: str) -> dict[str, dict[str, Any]]:
    """Canonical W-id -> {title, year, meta_goal?} from the structural shard (ladders) with the
    raw works file as the fallback for ladderless members. Handles both shapes mechanically."""
    root = Path(repo_root)
    out: dict[str, dict[str, Any]] = {}
    raw = root / _RAW / f"{key}_works.json"
    if raw.is_file():
        try:
            data = json.loads(raw.read_text(encoding="utf-8"))
            works = data if isinstance(data, list) else data.get("works", [])
            for w in works:
                m = re.match(r"(W\d+)", str(w.get("id", "")).rsplit("/", 1)[-1])
                if m:
                    out.setdefault(m.group(1), {"title": w.get("title", ""),
                                                "year": w.get("year") or w.get("publication_year", "")})
        except (OSError, json.JSONDecodeError):
            pass
    shard = root / _STRUCT / f"{key}.json"
    if shard.is_file():
        try:
            for lad in json.loads(shard.read_text(encoding="utf-8")).get("ladders", []):
                m = re.match(r"(W\d+)", str(lad.get("id", "")))
                if m:
                    rec = out.setdefault(m.group(1), {})
                    rec["title"] = lad.get("title", rec.get("title", ""))
                    rec["meta_goal"] = lad.get("meta_goal", "")
        except (OSError, json.JSONDecodeError):
            pass
    return out


def structural_parent(node_id: str) -> str | None:
    """The nested ladder parent: a ``//`` id -> the segment above it; a generator id
    (``<_structural file>::<slug>``) -> its file node. Checked BEFORE ``atom_parent`` so the
    ladder is preserved (atom_parent's single ``::`` split would flatten every level to the file)."""
    if NEST_SEP in node_id and "::" in node_id.split(NEST_SEP, 1)[0]:
        return node_id.rsplit(NEST_SEP, 1)[0]
    if "::" in node_id and "_structural/" in node_id.split("::", 1)[0]:
        return node_id.split("::", 1)[0]
    return None


def structural_leaves(repo_root: Path | str) -> dict[str, dict[str, Any]]:
    """Materialise every regraded ladder: authored generator/rung nodes (response-function
    essences, kept verbatim - the act-sufficient handles the closure gate passed) + paper
    leaves (title + meta-goal handle; the full ladder stays on disk, reconstruction re-reads)."""
    out: dict[str, dict[str, Any]] = {}
    for relpath, rec in _records(repo_root):
        key = rec.get("_key", "")
        titles = _titles(repo_root, key)
        for g in rec.get("generators", []):
            gid = f"{relpath}::{_slug(g.get('label', ''))}"
            out[gid] = {"kind": "program-generator", "essence": (g.get("essence") or "").strip(),
                        "keywords": _tokens(g.get("label", "") + " " +
                                            " ".join(r.get("name", "") for r in g.get("rungs", [])))[:14],
                        "sealed": False}
            for r in g.get("rungs", []):
                rid = f"{gid}{NEST_SEP}{r.get('name', '')}"
                out[rid] = {"kind": "program-rung", "essence": (r.get("essence") or "").strip(),
                            "keywords": _tokens(r.get("name", "") + " " + (r.get("essence") or "")[:200])[:14],
                            "sealed": False}
                for w in r.get("papers", []):
                    t = titles.get(w, {})
                    title = (t.get("title") or "").strip()
                    goal = (t.get("meta_goal") or "").strip()
                    essence = (f"{title} ({t.get('year','')}) - {goal}".strip(" -")
                               if title else f"{w} - member of {r.get('name','')} (no ladder yet)")
                    out[f"{rid}{NEST_SEP}{w}"] = {
                        "kind": "program-paper", "essence": essence[:480],
                        "keywords": _tokens(f"{title} {goal}")[:14] or _tokens(r.get("name", ""))[:8],
                        "sealed": False}
    return out


def structural_edge_index(repo_root: Path | str) -> dict[str, list[str]]:
    """Structural referents for ``build_reach``: paper -> its RUNG, rung -> its GENERATOR
    (containment coupling, no vocabulary leak), and generator <-> the author's person file
    (when one exists) via a shared ``xcorpus::`` token on both ends - the program couples to
    its person the same way the collaborator lens couples people to the physics they co-built."""
    idx: dict[str, list[str]] = {}
    root = Path(repo_root)
    for relpath, rec in _records(repo_root):
        person = f"{_PEOPLE}{rec.get('_key', '')}.md"
        person_exists = (root / person).is_file()
        for g in rec.get("generators", []):
            gid = f"{relpath}::{_slug(g.get('label', ''))}"
            idx.setdefault(gid, []).append(f"inprogram::{relpath}")
            if person_exists:
                token = f"xcorpus::{person}<->{gid}"
                idx.setdefault(gid, []).append(token)
                idx.setdefault(person, []).append(token)
            for r in g.get("rungs", []):
                rid = f"{gid}{NEST_SEP}{r.get('name', '')}"
                idx.setdefault(rid, []).append(f"ingen::{gid}")
                for w in r.get("papers", []):
                    idx.setdefault(f"{rid}{NEST_SEP}{w}", []).append(f"inrung::{rid}")
    return idx
