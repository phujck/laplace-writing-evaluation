"""The distillate lens - the mechanical join between a paper's DESCENT-REACHABLE leaves and the
rich distillate layer that hangs off the same paper elsewhere in the corpus.

WHY THIS EXISTS (the blind surfacing test, 2026-08-20, evidence/SELF_AUDIT_2026-08-20/blind_surfacing/).
Three blind agents were asked to reconstruct a paper from structure alone. They DID recover
arcana-grain content - mechanism, metric, numbers, apparatus, scope limits - but they found it by
essence-grep, not by descent: the ``concept_corpus`` atoms, the ``collaborator_corpus`` program
ladder's OpenAlex paper handles and the per-paper ``corpus_stores`` rows were unreachable from the
paper's own tex leaf. The measured cause is structural, and sharper than "a missing edge":

  * ``recursive_read.open_descender`` descends ``.meaning_tree.json``, and that tree is the RESIDUE
    tree - ``keeper.build_self`` clusters by meaning only what NO lens claims. Every ``::`` sub-node
    is lens-claimed by construction (``concept_lens.atom_parent`` /
    ``structural_lens.structural_parent``), so all 7,073 of them - the whole concept-atom and
    program-ladder layer - are absent from the descender's tree and can NEVER be a descent hit.
  * What IS reachable from a paper query is its tex leaf, its ``life_corpus`` paper node and its
    per-paper ``corpus_stores`` rows - and the store rows carry the essence ``"jsonl asset"``, so
    they sit in the tree effectively invisible.

So the cure is NOT a new store and NOT a parallel index: it is a typed WIRE on the one channel the
readers already ride - the substrate edge-index that ``keeper_ring.build_reach`` folds into ``reach``
and that ``conceptric.lateral`` / ``coupling_directed`` / ``embed_router.route`` all read. Every
member of one paper's family (tex leaves, store rows, life node, concept atoms, theme/connectome
handles, the collaborator W-nodes) is minted the SAME referent token,
``distillate_edge::<paper_id>``. Two nodes that share it couple; the token is distinctive enough
(a handful of nodes out of ~21k) to clear ``conceptric``'s lone-token IDF floor on its own. A
descent that lands on the paper's tex leaf therefore hands its reader the distillate node ids in
the leaf's NEIGHBOURHOOD - which is the reachability the blind test found missing.

THE FALLBACK HAZARD, handled explicitly. ``build_reach`` sets a leaf's reach to
``edge_targets or coverage`` - so giving its FIRST edge to a previously edgeless node would REPLACE
its keyword-fallback reach rather than extend it. ``corpus_stores/*`` rows and ``life_corpus/papers/*``
nodes are exactly such nodes. ``distillate_edge_index`` therefore re-emits an edgeless node's own
shard keywords alongside the new token, so the wire only ever ADDS substrate - but only its
DISTINCTIVE keywords (``GUARD_MAX_DOCFREQ``), because reach size IS the ``out`` denominator and
re-emitting a node's path words buries the family it was wired to reach. The measurement is in
``distillate_edge_index``.

THE PUBLISHED-ARTEFACT LEGS. A slug query for a paper with no tex directory lands on the paper's
own pdf or its archived abstract text, not on anything the tex/store legs cover - so the hit sat
OUTSIDE the family and the neighbourhood step never fired (6 papers, 98 atoms stranded,
``evidence/BLIND_SURFACING_RERUN_2026-08-20/`` s4). ``published_corpus/pdfs``,
``archive/soul_dump/my papers`` and ``archive/soul_dump/txt/abstracts`` therefore join on the same
normalized-title key as the life leg - truncation-tolerantly, because a file name carries a title
cut to fit the filename and is routinely the SHORTER side of the comparison.

THE EXEMPLAR LEG, and the escaped-character key (2026-08-20, the pinned re-run's two false misses).
``voice_corpus/exemplars/<paper_id>/`` holds a paper's own source when ``published_corpus/tex`` has
none; it joins by exact id, like tex. And a file name may carry a NON-ASCII character escaped into
the name itself (``Non#U2010Uniqueness``), which normalizes to letters rather than falling out as
punctuation - so ``_norm`` decodes ``#Uxxxx`` before tokenizing. Both papers returned their OWN
source or pdf at rank 1 and still read as descent misses on the standing bench; they are not.

THE MATCH, and what "reviewed once" means. The join key is the normalized title. A tex directory
name IS a truncated title-slug, so an exact PREFIX match against a candidate's title is the strong
signal (confidence 1.0); a difflib ratio over the same normalized strings, gated at
``FUZZY_FLOOR`` with a clear ``FUZZY_MARGIN`` over the runner-up, is the weak one. Candidates that
tie, or that span two DIFFERENT normalized titles, are ambiguous and are NOT applied - they are
listed for the operator in the match table (``scripts/wire_distillates.py``). Several distinct
OpenAlex W-ids sharing ONE normalized title are duplicate records of one work, not an ambiguity,
and all of their node ids are wired.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

# the one referent grammar this lens mints - a paper-family coupling token, minted identically on
# every member so `coupling(a, b)` counts the family they share, never their bag of path words.
DISTILLATE_PREFIX = "distillate_edge::"

TEX_ROOT = "published_corpus/tex"
# THE EXEMPLAR LEG (2026-08-20, FIND/WO-20260820-family-table-misses-two-legs). The voice corpus
# keeps a paper's own source under `voice_corpus/exemplars/<paper_id>/` for papers whose tex was
# never copied into `published_corpus/tex`. That directory is the node a slug query LANDS on for
# such a paper (`polaron-imposters` returns it at rank 1) - so without this leg the hit sits
# outside the family, the neighbourhood step never fires, and the paper reads as a descent miss it
# is not. The directory name IS the paper_id, so this leg needs no title matching, exactly like tex.
EXEMPLARS_ROOT = "voice_corpus/exemplars"
STORES_ROOT = "corpus_stores"
LIFE_PAPERS = "life_corpus/papers"
ATOMS_ROOT = "concept_corpus/atoms"
THEMES_ROOT = "concept_corpus/themes"
CONNECTOME_ROOT = "concept_corpus/connectome"

# THE PUBLISHED-ARTEFACT LEGS (2026-08-20, the blind-surfacing re-run's measured residual). A slug
# query for a paper with no tex directory lands on the paper's OWN pdf or its abstract text - and
# those roots were outside the family, so the neighbourhood step never fired and the whole
# distillate layer stayed stranded (6 papers, 98 atoms, evidence/BLIND_SURFACING_RERUN_2026-08-20/
# section 4). These are those roots.
PDFS_ROOT = "published_corpus/pdfs"
ARCHIVE_PAPERS_ROOT = "archive/soul_dump/my papers"
ARCHIVE_ABSTRACTS_ROOT = "archive/soul_dump/txt/abstracts"
# leg name -> the roots it is drawn from; one match, partitioned by where the file lives
FILE_LEG_ROOTS: dict[str, tuple[str, ...]] = {
    "pdf": (PDFS_ROOT,),
    "archive": (ARCHIVE_PAPERS_ROOT, ARCHIVE_ABSTRACTS_ROOT),
}

FUZZY_FLOOR = 0.90      # a fuzzy title match below this is not a match at all
FUZZY_MARGIN = 0.05     # ... and one whose runner-up is this close is AMBIGUOUS, not applied
# the truncation-tolerant branch compares only the overlap of two truncated slugs, so it needs a
# floor on that overlap - below this many characters a "prefix" is a coincidence, not a title.
TRUNC_MIN_OVERLAP = 20

# THE GUARD'S DISTINCTIVENESS CAP (2026-08-20, measured - see `distillate_edge_index`). The
# edgeless-node fallback re-emits a wired node's own coverage so the wire never REPLACES reach;
# it may re-emit only the DISTINCTIVE part of it. A keyword present in more than this fraction of
# the graded tree is location, not content ("pdf", "corpus", "mccaul", "et", "al"), and re-emitting
# it inflates the node's reach denominator - which is the whole of `coupling_directed`'s `out` -
# and buries the family's own atoms under every node that happens to share a path word.
GUARD_MAX_DOCFREQ = 0.002

# an unladdered structural member's essence is a placeholder, never a title
_PLACEHOLDER_RE = re.compile(r"^W\d+ - member of ")

# A NON-ASCII CHARACTER ESCAPED INTO THE FILE NAME ITSELF, not into some encoding of it. The
# archive's exporter wrote `Non#U2010Uniqueness` on disk for `Non‐Uniqueness` (U+2010 HYPHEN), and
# the escape survives into the node id. Left alone it normalizes to the LETTERS `u2010`, which is
# not punctuation and does not fall out - `non-u2010uniqueness-...` disagrees with the paper's slug
# at character four, so the truncation-tolerant prefix test fails and the paper's OWN pdf cannot
# join its own family (measured: FIND-20260820-non-uniqueness-reach-lost, 4 -> 0 reached nodes).
_CHAR_ESCAPE_RE = re.compile(r"#U([0-9A-Fa-f]{4})")


def _norm(text: str) -> str:
    """The join key: lowercase alphanumeric tokens, hyphen-joined. Punctuation, case and
    separator style all fall out, so 'Super-sensing: 100-Fold enhancement in THz time-domain'
    and the directory name 'super-sensing-100-fold-enhancement-in-thz-time-domain' meet.

    ``#Uxxxx`` escapes are decoded to the character they name FIRST (see ``_CHAR_ESCAPE_RE``), so a
    file name carrying an escaped dash normalizes to the same key as the title it is a copy of."""
    decoded = _CHAR_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text or "")
    return "-".join(re.findall(r"[a-z0-9]+", decoded.lower()))


def _score(key: str, candidate: str) -> float:
    """1.0 when the candidate's normalized title STARTS WITH the (truncated) key - the strong
    signal, because a tex directory name is a title-slug cut to length. Otherwise a difflib ratio
    over the candidate truncated to the key's length, so a long title is never penalised for the
    tail the directory name dropped."""
    if not key or not candidate:
        return 0.0
    if candidate.startswith(key):
        return 1.0
    return difflib.SequenceMatcher(None, key, candidate[:len(key)]).ratio()


def _shares_prefix(key: str, candidate: str) -> bool:
    """The truncation-tolerant prefix test: the two slugs agree over their whole OVERLAP, whichever
    of them is shorter. The title-bearing legs (life, collaborator) carry full titles, so one-sided
    ``candidate.startswith(key)`` suffices there; a FILE name carries a title cut to fit the
    filename ("… - 2022 - Sequential optical response suppression for chemic.pdf"), so the
    candidate is routinely the SHORTER side and the one-sided test misses every such paper."""
    n = min(len(key), len(candidate))
    return n >= TRUNC_MIN_OVERLAP and key[:n] == candidate[:n]


def _near(key: str, titles: list[str], cutoff: float,
          tolerant: bool = False) -> list[tuple[float, str]]:
    """``[(score, title)]`` at or above ``cutoff``, best first - ``_score``'s fuzzy branch over
    many candidates. difflib's two cheap upper bounds (``real_quick_ratio`` on length alone, then
    ``quick_ratio`` on the multiset of characters) reject almost every candidate before the O(n*m)
    ratio runs, which is what keeps this join off the load path's clock: the collaborator side
    offers ~1,300 distinct titles per paper and the full-ratio-on-everything shape cost 1.7 s.

    ``tolerant`` scores the two slugs over their common overlap instead of over the key's whole
    length (the file legs, whose candidate side is a truncated title). It re-seeds ``seq2`` per
    candidate, so it is used only on the small file-name side (~30 titles), never on the ladder."""
    sm = difflib.SequenceMatcher()
    if not tolerant:
        sm.set_seq2(key)
    out: list[tuple[float, str]] = []
    for t in titles:
        if tolerant:
            n = min(len(key), len(t))
            if n < TRUNC_MIN_OVERLAP:
                continue
            sm.set_seq2(key[:n])
            sm.set_seq1(t[:n])
        else:
            sm.set_seq1(t[:len(key)])
        if sm.real_quick_ratio() < cutoff or sm.quick_ratio() < cutoff:
            continue
        r = sm.ratio()
        if r >= cutoff:
            out.append((r, t))
    return sorted(out, key=lambda p: (-p[0], p[1]))


def _pick(key: str, candidates: dict[str, str],
          tolerant: bool = False) -> tuple[list[str], float, str]:
    """``(ids, confidence, why)`` for the best group of candidates. ``candidates`` is
    ``{node_id: normalized_title}``. Every id sharing the WINNING normalized title is returned
    together (duplicate records of one work); a runner-up with a DIFFERENT title within
    ``FUZZY_MARGIN`` makes the pick ambiguous, and the caller must not apply it."""
    if not candidates:
        return [], 0.0, "no-candidate"
    by_title: dict[str, list[str]] = {}
    for nid, title in candidates.items():
        by_title.setdefault(title, []).append(nid)
    hit = _shares_prefix if tolerant else (lambda k, t: t.startswith(k))
    prefix = sorted(t for t in by_title if hit(key, t))
    if prefix:
        if len(prefix) > 1:                       # two DIFFERENT titles both claim the slug
            return [], 1.0, f"ambiguous-with:{prefix[1][:60]}"
        rivals = _near(key, [t for t in by_title if t != prefix[0]], 1.0 - FUZZY_MARGIN, tolerant)
        if rivals:
            return [], 1.0, f"ambiguous-with:{rivals[0][1][:60]}"
        return sorted(by_title[prefix[0]]), 1.0, "prefix"
    ranked = _near(key, list(by_title), FUZZY_FLOOR, tolerant)
    if not ranked:
        return [], 0.0, "below-floor"
    best_score, best_title = ranked[0]
    if len(ranked) > 1 and best_score - ranked[1][0] < FUZZY_MARGIN:
        return [], round(best_score, 4), f"ambiguous-with:{ranked[1][1][:60]}"
    return sorted(by_title[best_title]), round(best_score, 4), "fuzzy"


# ---------------------------------------------------------------------------
# the candidate sides - each read from its OWN home, never from the 18 MB graded shard
# ---------------------------------------------------------------------------

def _paper_id_dirs(repo_root: Path, root_rel: str) -> dict[str, list[str]]:
    """``paper_id -> the leaf node ids under ``<root_rel>/<paper_id>/``. The directory name IS the
    paper_id (it is also the ``paper_id`` the stage stores key by), so these legs are an exact id
    match and need no title comparison at all."""
    out: dict[str, list[str]] = {}
    root = repo_root / root_rel
    if not root.is_dir():
        return out
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        files = sorted(f"{root_rel}/{d.name}/{f.name}" for f in d.iterdir() if f.is_file())
        if files:
            out[d.name] = files
    return out


def _tex_dirs(repo_root: Path) -> dict[str, list[str]]:
    """``paper_id -> its tex leaf node ids`` (``published_corpus/tex/<paper_id>/``)."""
    return _paper_id_dirs(repo_root, TEX_ROOT)


def _exemplar_dirs(repo_root: Path) -> dict[str, list[str]]:
    """``paper_id -> its voice-corpus exemplar source ids`` (``voice_corpus/exemplars/<paper_id>/``)
    - the paper's own tex where ``published_corpus/tex`` has none. See ``EXEMPLARS_ROOT``."""
    return _paper_id_dirs(repo_root, EXEMPLARS_ROOT)


def _tex_manifest_titles(repo_root: Path) -> dict[str, str]:
    """``paper_id -> title`` for the papers whose tex was acquired but does NOT live under
    ``published_corpus/tex/<paper_id>/`` (``_manifest.json``'s ``existing_tex_papers``). Without
    this their families would have no join key but the bare id, which is not a title and matches
    nothing - and 8 real paper families, 31 stage-store rows, would go unwired."""
    out: dict[str, str] = {}
    m = repo_root / TEX_ROOT / "_manifest.json"
    if not m.is_file():
        return out
    try:
        data = json.loads(m.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    for p in data.get("existing_tex_papers", []):
        if p.get("paper_id") and p.get("title"):
            out[p["paper_id"]] = p["title"]
    return out


def _store_rows(repo_root: Path) -> dict[str, list[str]]:
    """``paper_id -> the per-paper stage-store row files`` (derivation_walk, spine_chain,
    section_architecture, figure_caption, paragraph_plan, ...). Keyed by the store's own
    ``paper_id``, so this leg needs no title matching at all."""
    out: dict[str, list[str]] = {}
    root = repo_root / STORES_ROOT
    if not root.is_dir():
        return out
    for stage in sorted(p for p in root.iterdir() if p.is_dir()):
        for f in sorted(stage.glob("*.jsonl")):
            if f.stem.startswith("_") or f.stem in {"embeddings", "corpus_verdict", "gate_verdict"}:
                continue
            out.setdefault(f.stem, []).append(f"{STORES_ROOT}/{stage.name}/{f.name}")
    return out


_TITLE_RE = re.compile(r"^#\s+(.+)$", re.M)


def _life_papers(repo_root: Path) -> dict[str, str]:
    """``life_corpus paper node id -> normalized title`` (the ``# <title>`` heading of the
    distilled episodic trace). Its slug is also the concept-atom slug, so this leg carries the
    concept layer in behind it."""
    out: dict[str, str] = {}
    root = repo_root / LIFE_PAPERS
    if not root.is_dir():
        return out
    for f in sorted(root.glob("*.md")):
        try:
            m = _TITLE_RE.search(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if m:
            out[f"{LIFE_PAPERS}/{f.name}"] = _norm(m.group(1))
    return out


def _file_title(name: str) -> str:
    """The normalized title carried by a published-artefact FILE name. The house convention is
    ``<authors> - <year> - <title cut to fit>.<ext>``; anything that does not carry those three
    fields (``txt/full/waveop2023.txt``) yields its bare stem, which will not clear the overlap
    floor against a real title-slug and so joins nothing."""
    stem = name.rsplit(".", 1)[0]
    parts = stem.split(" - ")
    return _norm(parts[-1] if len(parts) >= 3 else stem)


def _paper_files(repo_root: Path) -> dict[str, str]:
    """``node id -> normalized (truncated) title`` for every file under the published-artefact
    roots - the paper's own pdf and the archived pdf/abstract text. These are the nodes a slug
    query LANDS on for a paper with no tex directory, so without this leg the descent's hit sits
    outside the family and the whole rich layer stays one edge away with nothing crossing."""
    out: dict[str, str] = {}
    for roots in FILE_LEG_ROOTS.values():
        for root in roots:
            d = repo_root / root
            if not d.is_dir():
                continue
            for f in sorted(d.iterdir()):
                if f.is_file() and not f.name.startswith("."):
                    out[f"{root}/{f.name}"] = _file_title(f.name)
    return out


def _program_papers(repo_root: Path) -> dict[str, str]:
    """``collaborator program-paper node id -> normalized title``, straight off the regraded
    ladders (``structural_lens``' own sources, walked here for titles only so nothing has to
    materialise 1,700 leaf dicts). Unladdered placeholder members are dropped - their essence is
    an id, not a title, and it must never join anything."""
    from laplace.engine import structural_lens
    out: dict[str, str] = {}
    for relpath, rec in structural_lens._records(repo_root):
        titles = structural_lens._titles(repo_root, rec.get("_key", ""))
        for gen in rec.get("generators", []):
            gid = f"{relpath}::{structural_lens._slug(gen.get('label', ''))}"
            for rung in gen.get("rungs", []):
                rid = f"{gid}{structural_lens.NEST_SEP}{rung.get('name', '')}"
                for w in rung.get("papers", []):
                    title = (titles.get(w, {}).get("title") or "").strip()
                    if not title or _PLACEHOLDER_RE.match(title):
                        continue
                    out[f"{rid}{structural_lens.NEST_SEP}{w}"] = _norm(title)
    return out


def _atom_nodes(repo_root: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """``(concept slug -> its g0 atom node ids, concept slug -> its theme)`` from the atoms
    manifest - the same containment ``concept_lens.atom_to_paper`` hangs the lens floor on."""
    from laplace.engine import concept_lens
    atoms: dict[str, list[str]] = {}
    for aid, paper in concept_lens.atom_to_paper(repo_root).items():
        slug = paper[len(concept_lens._ATOMS):].removesuffix(".md")
        atoms.setdefault(slug, []).append(aid)
    themes: dict[str, str] = {}
    mpath = repo_root / "concept_corpus" / "_atoms_manifest.json"
    if mpath.is_file():
        try:
            for p in json.loads(mpath.read_text(encoding="utf-8")).get("papers", []):
                if p.get("slug") and p.get("theme"):
                    themes[p["slug"]] = p["theme"]
        except (OSError, ValueError):
            pass
    return {k: sorted(v) for k, v in atoms.items()}, themes


# ---------------------------------------------------------------------------
# the match table - the reviewable object, and the thing the edge index is derived FROM
# ---------------------------------------------------------------------------

def paper_families(repo_root: Path | str) -> dict[str, Any]:
    """The mechanical join, as a reviewable table.

    Returns ``{"matched": {paper_id: family}, "ambiguous": [...], "unmatched": [...],
    "counts": {...}}``. A ``family`` lists the node ids on every leg it resolved plus the
    per-leg confidence. ONLY ``matched`` families are wired; ``ambiguous`` legs are recorded with
    the reason so an operator can adjudicate them once, by hand, and nothing is applied on a
    guess. Pure derivation: same inputs, same table, no store of its own."""
    repo_root = Path(repo_root)
    tex = _tex_dirs(repo_root)
    exemplars = _exemplar_dirs(repo_root)
    stores = _store_rows(repo_root)
    life = _life_papers(repo_root)
    programs = _program_papers(repo_root)
    files = _paper_files(repo_root)
    atoms_by_slug, theme_by_slug = _atom_nodes(repo_root)

    matched: dict[str, dict[str, Any]] = {}
    ambiguous: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []

    # The family set is the tex directories UNION the stage stores' own paper_ids. A tex directory
    # name is already a title-slug, so it joins as itself; a store-only paper (its tex lives
    # elsewhere) has no title in its id, so its key comes from the tex manifest.
    manifest_titles = _tex_manifest_titles(repo_root)
    keys = {pid: _norm(pid) for pid in tex}
    for pid in list(exemplars) + list(stores):
        if pid not in keys:
            keys[pid] = _norm(manifest_titles.get(pid) or pid)

    for paper_id in sorted(keys):
        key = keys[paper_id]
        fam: dict[str, Any] = {"paper_id": paper_id, "tex": tex.get(paper_id, []),
                               "exemplars": sorted(exemplars.get(paper_id, [])),
                               "stores": sorted(stores.get(paper_id, [])),
                               "confidence": {"stores": "exact-paper-id" if stores.get(paper_id)
                                              else "none",
                                              "exemplars": "exact-paper-id"
                                              if exemplars.get(paper_id) else "none"}}
        life_ids, life_conf, life_why = _pick(key, life)
        if life_ids:
            fam["life"] = life_ids
            fam["confidence"]["life"] = {"score": life_conf, "why": life_why}
            slug = Path(life_ids[0]).stem
            fam["concept_slug"] = slug
            if atoms_by_slug.get(slug):
                fam["atoms"] = atoms_by_slug[slug]
                fam["atom_paper"] = f"{ATOMS_ROOT}/{slug}.md"
            theme = theme_by_slug.get(slug)
            if theme:
                fam["theme"] = [f"{THEMES_ROOT}/{theme}.md", f"{CONNECTOME_ROOT}/{theme}.md"]
        elif life_why.startswith("ambiguous"):
            ambiguous.append({"paper_id": paper_id, "leg": "life", "why": life_why,
                              "score": life_conf})

        prog_ids, prog_conf, prog_why = _pick(key, programs)
        if prog_ids:
            fam["collaborator"] = prog_ids
            fam["confidence"]["collaborator"] = {"score": prog_conf, "why": prog_why,
                                                 "n_openalex_ids": len({p.rsplit('//', 1)[-1]
                                                                        for p in prog_ids})}
        elif prog_why.startswith("ambiguous"):
            ambiguous.append({"paper_id": paper_id, "leg": "collaborator", "why": prog_why,
                              "score": prog_conf})

        # the published-artefact legs: ONE truncation-tolerant match over all three roots, then
        # partitioned by where each file lives, so pdf and archive are named separately in the
        # table while sharing a single adjudicated title decision.
        file_ids, file_conf, file_why = _pick(key, files, tolerant=True)
        if file_ids:
            for leg, roots in FILE_LEG_ROOTS.items():
                got = sorted(i for i in file_ids if i.startswith(roots))
                if got:
                    fam[leg] = got
                    fam["confidence"][leg] = {"score": file_conf, "why": file_why}
        elif file_why.startswith("ambiguous"):
            ambiguous.append({"paper_id": paper_id, "leg": "published_files", "why": file_why,
                              "score": file_conf})

        if (fam.get("life") or fam.get("collaborator") or fam.get("stores")
                or fam.get("pdf") or fam.get("exemplars")):
            matched[paper_id] = fam
        else:
            unmatched.append({"paper_id": paper_id, "why": "no distillate leg resolved",
                              "life": life_why, "collaborator": prog_why})

    counts = {
        "tex_papers": len(tex),
        "families_considered": len(keys),
        "store_only_papers": len(keys) - len(tex),
        "matched": len(matched),
        "ambiguous": len(ambiguous),
        "unmatched": len(unmatched),
        "with_concept_atoms": sum(1 for f in matched.values() if f.get("atoms")),
        "with_collaborator": sum(1 for f in matched.values() if f.get("collaborator")),
        "with_stores": sum(1 for f in matched.values() if f.get("stores")),
        "with_exemplars": sum(1 for f in matched.values() if f.get("exemplars")),
        "with_pdf": sum(1 for f in matched.values() if f.get("pdf")),
        "with_archive": sum(1 for f in matched.values() if f.get("archive")),
        "wired_nodes": len({n for f in matched.values() for n in family_members(f)}),
    }
    return {"schema": "distillate-edge-match/0.1", "prefix": DISTILLATE_PREFIX,
            "matched": matched, "ambiguous": ambiguous, "unmatched": unmatched, "counts": counts}


def family_members(family: dict[str, Any]) -> list[str]:
    """Every node id a matched family wires, deduped and ordered - the exact set that is minted
    the family's ``distillate_edge::`` referent."""
    ids: list[str] = []
    for leg in ("tex", "exemplars", "stores", "life", "atoms", "theme", "collaborator",
                "pdf", "archive"):
        ids.extend(family.get(leg) or [])
    if family.get("atom_paper"):
        ids.append(family["atom_paper"])
    return sorted(set(ids))


# ---------------------------------------------------------------------------
# the wire itself - what `conceptric._self_edge_index` merges
# ---------------------------------------------------------------------------

def _coverage_docfreq(nodes: dict[str, dict[str, Any]] | None) -> tuple[dict[str, int], int]:
    """``(keyword -> how many nodes carry it, node count)`` over the graded tree's own coverage -
    the guard's distinctiveness universe. One O(N) pass, computed where the tree is already in
    hand rather than threaded in from the caller."""
    df: dict[str, int] = {}
    for node in (nodes or {}).values():
        for kw in set(node.get("coverage") or node.get("keywords") or []):
            df[kw] = df.get(kw, 0) + 1
    return df, len(nodes or {})


def _distinctive(node: dict[str, Any], df: dict[str, int], n_nodes: int) -> list[str]:
    """A node's coverage keywords that are distinctive enough to be worth re-emitting - the ones
    at or below ``GUARD_MAX_DOCFREQ`` of the tree. Order preserved; nothing else filtered. The
    ceiling never falls below 1: a keyword no other node carries is distinctive by definition, and
    without the floor a small tree (a test's four nodes, a fresh corpus) would re-emit nothing."""
    ceiling = max(1.0, GUARD_MAX_DOCFREQ * n_nodes)
    return [kw for kw in (node.get("coverage") or node.get("keywords") or [])
            if df.get(kw, 0) <= ceiling]


def distillate_edge_index(repo_root: Path | str,
                          base: dict[str, list[str]] | None = None,
                          nodes: dict[str, dict[str, Any]] | None = None,
                          table: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """``node id -> its distillate referents`` for ``keeper_ring.build_reach``.

    Every member of a MATCHED paper family is minted the identical ``distillate_edge::<paper_id>``
    token, so ``coupling(tex_leaf, concept_atom)`` counts the paper they actually share. Ambiguous
    and unmatched families contribute nothing.

    ``base`` (the edge index merged so far) and ``nodes`` (the graded tree) are the fallback guard
    described in the module docstring: for a member that has NO prior edge, its own
    ``coverage``/``keywords`` are re-emitted alongside the new token, because ``build_reach`` reads
    ``edge_targets OR coverage`` and would otherwise REPLACE the keyword reach this node used to
    couple on rather than extend it. Measured on the live corpus without the guard: 87 of the 362
    wired nodes silently lost reach tokens, 88 of the 89 distinct tokens dropped sitting BELOW the
    lone-token IDF floor (i.e. distinctive enough that they had been carrying real edges). With the
    guard the wire is strictly additive. Without either argument the guard is skipped and the token
    is still minted - stated here rather than silently assumed.

    THE GUARD RE-EMITS THE DISTINCTIVE COVERAGE ONLY (2026-08-20, the blind-surfacing re-run's
    residual (b)). The first cut re-emitted ALL of it, and that cost distillate RANK on exactly the
    nodes it protected: ``life_corpus/papers/twinning-fields-2021.md`` came back with a 10-token
    reach of which 9 were path words, so every concept atom scored ``out = 1/10`` while any node
    sharing two path words scored ``0.2`` and crowded the family out at every width to 200. The
    same disease sat on the pdf/archive legs: a paper's own pdf carried 13 tokens, 9 of them
    ``pdf``/``pdfs``/``corpus``/``mccaul``/``et``/``al``. Cure: re-emit a keyword only if it is
    present in at most ``GUARD_MAX_DOCFREQ`` of the tree - which is precisely the class the guard's
    own measurement named as worth protecting (distinctive tokens carrying real edges), and
    excludes the class that only inflates the denominator. Measured on the 25-paper harness, cap
    swept none/2%/1%/0.5%/0.2%/0.1%/0: papers reaching their atoms at width 60 goes 6 -> 8 -> 9 ->
    14 -> 14 -> 14 -> 14, and the elbow at 0.2% is where width 20 also reaches all of them; past it
    reach is spent for nothing."""
    repo_root = Path(repo_root)
    table = table if table is not None else paper_families(repo_root)
    guard_on = base is not None and nodes is not None
    cap = _coverage_docfreq(nodes) if guard_on else ({}, 0)
    idx: dict[str, list[str]] = {}
    for paper_id, fam in table.get("matched", {}).items():
        token = f"{DISTILLATE_PREFIX}{paper_id}"
        for nid in family_members(fam):
            bucket = idx.setdefault(nid, [])
            if token not in bucket:
                bucket.append(token)
            if guard_on and not base.get(nid):
                node = (nodes or {}).get(nid) or {}
                for kw in _distinctive(node, *cap):
                    if kw not in bucket:
                        bucket.append(kw)
    return idx
