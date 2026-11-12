"""The cross-lens identity resolver - the operator that fuses an entity's per-lens portraits into
ONE apex ring (his build, 2026-06-13). Recall, the navigator, and generation all read the same
network; until now an entity folded into separate, disjoint atom sets per corpus (the soul self,
the physics collaborator, the engine/voice author) and they never coupled, because coupling rides
SHARED REACH and the portraits share none. So reconstructing "the author" returned several
lens-local fragments that the orchestrator (a model, in the seam) had to ring up by hand - the gap
the recall test exposed.

This closes the seam mechanically. It runs as a build-time overlay (sibling of ``_soul_overlay`` /
``_mind_overlay`` in ``conceptric.load_network``), so every ``interesting`` (ingest) and ``sew up``
(close) that rebuilds the network re-resolves and the unified apex enriches itself - automatic, no
hand in the loop. For each resolved entity it:

  1. emits a ``person://<key>`` apex whose MEMBERS are the per-lens portraits and whose REACH is
     their union - a hot hub a broad pull surfaces, descending to every lens (the recall ring-down);
  2. injects ONE synthetic identity atom ``identity::<key>`` into every member's reach, so the
     portraits couple to one another through the EXISTING coupling formula - no new coupling logic.
     This is the load-bearing move: the unification surfaces on the same ``reach`` that the
     generation pull reads, so when a piece fires to generate, the pull reaches his correlates
     across lenses (his hope: the pieces think with his correlates), not just a recall-only field;
  3. stamps each member with ``identities = [person://<key>]`` - the ring-UP handle from a portrait
     to its apex, surfaced by ``reconstruct_node`` (the portrait's own ``parent`` is left untouched,
     so its native tree is intact; the identity apex is an ADDITIONAL uplink, not a reparenting).

The resolution key is derived from the data, never decreed: the author from the ``is_author`` flag
plus the name tokens it carries (so ``mccaul`` resolves to the author but ``james_mccaul``, his
brother, does not - his tokens are not a subset); everyone else by exact normalized name across
their portraits. High-precision: a group is only fused when it spans >=2 lenses, and the overlay is
recoverable (it writes nothing to the floor)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

PERSON_PREFIX = "person://"
_IDENTITY_ATOM = "identity::"            # the synthetic shared-reach atom that couples the portraits
IDENTITY_LENS = "identity"


def _toks(s: str) -> frozenset[str]:
    """An identity's alphabetic token set - the normaliser that collapses ``_`` / ``-`` / case so
    ``denys_bondar`` (soul) and ``denys-bondar`` (life) read as one person, and ``Gerard McCaul``
    yields ``{gerard, mccaul}``."""
    return frozenset(t for t in re.findall(r"[a-z]+", s.lower()) if len(t) > 1)


def _stem(nid: str) -> str:
    return nid.rsplit("/", 1)[-1]


# fold-artifact tokens, not name parts: a collaborator's `_structural/<name>_regraded.json` etc. is
# the SAME person seen through a build stage, so these tokens are stripped before keying - otherwise
# every regrade variant becomes its own "person" and pollutes the merge with ambiguous supersets.
_STRUCTURAL_TOKENS = frozenset({
    "raw", "regrade", "regraded", "general", "closure", "substrate", "distillate", "distillates",
    "voice", "structural", "promote", "refine", "round", "validation", "cluster", "basis", "openq",
    "reclassified", "self", "plus", "authored", "corpus", "json", "group",
})


def _author_signal(repo_root: Path) -> tuple[set[str], set[str], str]:
    """Derive the author's identity from the data: the stems of the ``is_author`` soul entities, the
    union of their NAME tokens, and the author's FIRST name (the unique discriminator - the brother
    shares the surname, not the first name). Returns (author_stems, author_name_tokens, first) -
    never hardcoded."""
    stems: set[str] = set()
    name_toks: set[str] = set()
    first = ""
    try:
        from laplace.engine import soul_provenance
        for stem, (_p, d) in soul_provenance.entities_by_stem(repo_root).items():
            if d.get("is_author"):
                stems.add(stem)
                nm = str(d.get("name") or "")
                name_toks |= _toks(nm)
                parts = _toks(nm.split()[0]) if nm.split() else frozenset()
                first = first or (sorted(parts)[0] if parts else "")
    except Exception:                    # noqa: BLE001 - no soul layer is fine; author then only via markers
        pass
    return stems, name_toks, first


def _is_author_marker(nid: str) -> bool:
    """The engine/voice/self-record nodes that ARE the author (about him, in his own corpus) - the
    portraits the name-token rule cannot see because they are filed under 'author', not his name."""
    return (nid == "EIGEN_AUTHOR.md" or "/wiki/author/" in nid
            or "voice_corpus/author_" in nid)


def _name_key(toks: frozenset[str]) -> str | None:
    """A person key from a token set: drop the fold-artifact tokens, sort the name parts. None if
    nothing survives (a pure structural node like ``raw_regrade`` is not a person)."""
    name = sorted(toks - _STRUCTURAL_TOKENS)
    return "-".join(name) if name else None


def _identity_key(nid: str, author_stems: set[str], author_name_toks: set[str],
                  author_first: str, author_key: str) -> str | None:
    """The entity a node is a portrait OF, as a normalized key - or None if the node is not a
    resolvable entity portrait. Author detection is conservative and uses the FIRST name as the
    family discriminator: the ``is_author`` soul stems, the explicit author markers, any soul
    entity carrying his first name (his reclassified chat-self), his surname inside his OWN
    collaborator corpus (``mccaul_closure`` etc.), or a token-subset of his full name. The brother
    (``james mccaul``: surname but not first name, and only in the soul) is correctly NOT the author."""
    from laplace.engine.conceptric import SOUL_ENTITIES_PARENT
    if _is_author_marker(nid):
        return author_key
    if "::" in nid:                                          # nested program atoms, not entity portraits
        return None
    if nid.startswith(SOUL_ENTITIES_PARENT + "/"):
        if nid.count("/") > SOUL_ENTITIES_PARENT.count("/") + 1:   # a sealed field item (.../voice/3)
            return None
        stem = _stem(nid)
        toks = _toks(stem)
        if stem in author_stems or (author_first and author_first in toks):
            return author_key
        return _name_key(toks)
    if nid.startswith("collaborator") or nid.startswith("life_corpus/people/"):
        stem = _stem(nid).replace(".json", "").replace(".md", "")
        toks = _toks(stem)
        if not toks:
            return None
        # the collaborator_corpus is the author's OWN principal program: a variant there carrying his
        # surname is HIM (the brother lives only in the soul, never here).
        if author_name_toks and nid.startswith("collaborator") and (toks & author_name_toks):
            return author_key
        if author_name_toks and toks <= author_name_toks:
            return author_key
        return _name_key(toks)
    return None


def resolve(repo_root: Path | str, nodes: dict[str, dict[str, Any]],
            reach: dict[str, set[str]], lenses: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Group the entity portraits by identity key, keep the groups that span >=2 lenses, and return
    one descriptor per resolved person: {key, person_id, members, lenses}. Pure - the caller mutates
    the network (so the resolution is testable apart from the mutation)."""
    repo_root = Path(repo_root)
    author_stems, author_name_toks, author_first = _author_signal(repo_root)
    author_key = "-".join(sorted(author_name_toks)) if author_name_toks else "gerard-mccaul"

    groups: dict[str, list[str]] = {}
    for nid in list(nodes):
        key = _identity_key(nid, author_stems, author_name_toks, author_first, author_key)
        if key:
            groups.setdefault(key, []).append(nid)

    # subset-merge: a name variant that is a PROPER token-subset of exactly one other key is the same
    # person seen with fewer name parts (life's 'bondar' is soul's 'denys_bondar'). Merge into the
    # UNIQUE superset only - an ambiguous subset (two supersets) is left split rather than risk a
    # false merge. The author is anchored separately above, so it never participates here.
    keytoks = {k: frozenset(k.split("-")) for k in groups}
    for sub in sorted(groups, key=lambda k: len(keytoks[k])):
        if sub == author_key:
            continue
        supers = [k for k in groups if k != sub and keytoks[sub] < keytoks[k] and k != author_key]
        if len(supers) == 1:
            groups[supers[0]].extend(groups.pop(sub))

    persons: list[dict[str, Any]] = []
    for key, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        lens_union = sorted({L for m in members for L in lenses.get(m, [])})
        if len(lens_union) < 2:                              # not genuinely cross-lens - skip
            continue
        persons.append({"key": key, "person_id": PERSON_PREFIX + key,
                        "members": sorted(members), "lenses": lens_union})
    return persons


def identity_overlay(repo_root: Path | str, nodes: dict[str, dict[str, Any]],
                     reach: dict[str, set[str]], lenses: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Attach the resolved person apexes to the network IN PLACE (the build-time hook). For each
    person: emit ``person://<key>`` (members = portraits, reach = union + the identity atom), inject
    the identity atom into every member's reach (the cross-lens coupling), and stamp every member's
    ``identities`` uplink. Returns the person descriptors for logging/tests. Guarded: a failure here
    must never break the network build."""
    try:
        persons = resolve(repo_root, nodes, reach, lenses)
    except Exception:                                        # noqa: BLE001 - the overlay is enrichment
        return []
    root_id = "" if "" in nodes else next((k for k, v in nodes.items() if v.get("parent") is None), "")
    for p in persons:
        key, pid, members = p["key"], p["person_id"], p["members"]
        idatom = _IDENTITY_ATOM + key
        name_kw = sorted(_toks(key))
        member_grades = [nodes[m].get("grade", 0) for m in members if m in nodes]
        grade = (max(member_grades) + 1) if member_grades else 1
        union: set[str] = {idatom}
        for m in members:
            if m not in nodes:
                continue
            reach[m] = set(reach.get(m, set())) | {idatom}   # the shared atom -> portraits now couple
            union |= reach[m]
            ident = list(nodes[m].get("identities") or [])
            if pid not in ident:
                ident.append(pid)
            nodes[m]["identities"] = ident                   # the ring-UP handle (parent left intact)
            nodes[m]["keywords"] = sorted(set(nodes[m].get("keywords") or []) | set(name_kw))
        nodes[pid] = {"id": pid, "grade": grade, "parent": root_id, "leaf": False,
                      "members": members, "coverage": name_kw, "keywords": name_kw,
                      "identity_apex": True, "resolved_lenses": p["lenses"],
                      "essence": (f"{key.replace('-', ' ')} - one person across "
                                  f"{len(p['lenses'])} lenses ({', '.join(p['lenses'])}); "
                                  "the cross-lens apex, members are the per-lens portraits")}
        reach[pid] = union
        # the person wears the identity badge AND its members' lenses, so a lens-local navigation
        # (e.g. the physics view) still surfaces the cross-lens apex - the unification is visible
        # from inside every lens it spans, not only from a dedicated identity view.
        lenses[pid] = [IDENTITY_LENS] + p["lenses"]
        if root_id in nodes and pid not in nodes[root_id].get("members", []):
            nodes[root_id].setdefault("members", []).append(pid)
    return persons
