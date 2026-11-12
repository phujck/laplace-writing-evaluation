"""soul_resolve.py - the SEALED *semantic* upward operator (the inter-grade scale-link).

The third soul organ. ``soul_shard`` grades DOWN (chunks); ``soul_consolidate`` grades UP
STRUCTURALLY (stream -> unit -> chunk, by source). This grades UP *SEMANTICALLY*: it lifts one node
ACROSS streams along a generated AXIS. The first axis is PERSON - entity resolution: the same person
on the paper and in the chat log is ONE node (the author's reframe; the privacy is the seal on the
raw, never anonymisation of the structure).

The author's law for this operator (2026-06-08): *the upward operator always transforms, but it is
the SCALE-LINKING operator, so the transform is set by the semantic content between the two grades -
it is always a task handled in an inter-grade operation.* So this module is the SCAFFOLD of that
task, not the judgement:

    gather   the grade-below members across corpora (sealed chunks by index PATH; public refs given)
    [LINK]   <- the semantic content between grades: is this one entity? what binds the members?
                produced by a sealed sub-eigen reading the sealed members, attached here - NEVER Python
    persist  the lifted node (rich LOCAL) + a content-free HANDLE (committed, refs-only)
    verify   the link closes (sampled faithfulness over the sealed members - never O(N^2))

The orchestrator never reads sealed content: ``gather`` matches on the index's source PATH and keeps
only metadata (ids, char-counts, line-range labels). The reading of the sealed chunks happens inside
the sealed sub; only its small distillate (the resolution) rises and is ``attach``-ed.

Privacy (F24), structural not remembered: the rich resolved node carries chat-DERIVED material and is
LOCAL (``archive/soul_dump/`` is gitignored). The committed handle goes under ``soul_corpus/sealed/``
(refs-only to the tools) and is built by ``_safe_handle``, which reads ONLY content-free / public
fields (real identity, public join evidence, member COUNTS, the verdicts) - never a line of sealed
content, never even a sealed member id. The seal is in the projection, so a careless caller cannot
leak through the handle.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import re
from pathlib import Path
from typing import Any

from laplace.engine import soul_shard

RESOLVED_LOCAL = "archive/soul_dump/_shard/resolved"   # gitignored - the rich resolved nodes
SEALED_HANDLES = "soul_corpus/sealed"                   # committed, refs-only - content-free handles


def _norm(s: str) -> str:
    """Fold case + collapse separators so an alias matches a folder/file path regardless of how the
    name was written (``Denys_Bondar`` / ``denys-bondar`` / ``Denys Bondar`` -> ``denys bondar``)."""
    return re.sub(r"[\s_\-]+", " ", s.lower()).strip()


# ---------------------------------------------------------------------------
# gather - the grade-below members across corpora (PATH-matched; no content read)
# ---------------------------------------------------------------------------

def _sealed_members(repo_root: Path | str, needles: list[str]) -> list[dict[str, Any]]:
    """Sealed (soul-dump) chunks whose SOURCE PATH carries the entity - matched on the gitignored
    soul-shard index, NEVER on content. Keeps metadata only (id, source, line-range label, char
    count, stream). This is the structural half of entity resolution - a person with their own
    landing folder (``chat_logs/Denys_Bondar/``). Mention-level resolution (a name inside a shared
    conversation) is the semantic sub's job, not this path match."""
    wants = {_norm(n) for n in needles if n and n.strip()}
    out: list[dict[str, Any]] = []
    for sh in soul_shard.load_local_index(repo_root):
        path_n = _norm(sh["source"])
        if any(w in path_n for w in wants):
            out.append({k: sh[k] for k in ("id", "source", "label", "n_chars", "category") if k in sh})
    return out


def gather(repo_root: Path | str, entity: dict[str, Any]) -> dict[str, Any]:
    """Assemble the lifted node's grade-below members. ``entity`` =
    {key, display_name, aliases[], public_refs[{ref,kind}], public_join[], negative_controls[], axis?}.
    The sealed members are found by path; the public members are supplied (life_corpus refs / arXiv
    join keys). ``resolution`` / ``adjudication`` are None until the sealed wave attaches them."""
    needles = list(entity.get("aliases", [])) + [entity["display_name"], entity["key"]]
    sealed = _sealed_members(repo_root, needles)
    public = list(entity.get("public_refs", []))
    return {
        "axis": entity.get("axis", "person"),
        "entity": entity["key"],
        "display_name": entity["display_name"],
        "aliases": list(entity.get("aliases", [])),
        "members": {"sealed": sealed, "public": public},
        "counts": {
            "sealed_chunks": len(sealed),
            "sealed_sources": len({m["source"] for m in sealed}),
            "public_refs": len(public),
        },
        "public_join": list(entity.get("public_join", [])),
        "negative_controls": list(entity.get("negative_controls", [])),
        "resolution": None,
        "adjudication": None,
    }


def attach(node: dict[str, Any], resolution: dict[str, Any] | None = None,
           adjudication: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach the semantic content between grades - the sealed sub's resolution and the judge's
    verdict. Pure merge; this is where the inter-grade LINK enters the otherwise-mechanical node."""
    if resolution is not None:
        node["resolution"] = resolution
    if adjudication is not None:
        node["adjudication"] = adjudication
    return node


# ---------------------------------------------------------------------------
# persist - rich LOCAL node (gitignored) + content-free HANDLE (committed, refs-only)
# ---------------------------------------------------------------------------

def write_local(repo_root: Path | str, node: dict[str, Any]) -> Path:
    """The full resolved node - incl. chat-derived resolution - to the gitignored local layer."""
    out = Path(repo_root) / RESOLVED_LOCAL / f"{node['axis']}_{node['entity']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(node, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _safe_handle(node: dict[str, Any]) -> dict[str, Any]:
    """Project the node to ONLY content-free / public fields - the seal made structural. Excludes
    every free-text field the sealed sub produced (identity profile, register, evidence prose) and
    even the sealed member ids/labels: only the COUNT of sealed members survives. What remains is
    real identity (the cross-corpus key, public), public join evidence (public), counts, verdicts."""
    res = node.get("resolution") or {}
    adj = node.get("adjudication") or {}
    return {
        "axis": node["axis"],
        "entity": node["entity"],
        "display_name": node["display_name"],
        "aliases": node["aliases"],
        "counts": node["counts"],
        "public_join": node.get("public_join", []),
        "public_refs": [m.get("ref") for m in node["members"]["public"] if m.get("ref")],
        "same_person": res.get("same_person"),
        "confidence": res.get("confidence"),
        "verdict": adj.get("verdict"),
        "negative_controls": node.get("negative_controls", []),
    }


def write_handle(repo_root: Path | str, node: dict[str, Any]) -> Path:
    """The committed, refs-only handle under ``soul_corpus/sealed/people/``. Built from
    ``_safe_handle`` so it cannot carry sealed content even if the caller is careless."""
    h = _safe_handle(node)
    out = Path(repo_root) / SEALED_HANDLES / "people" / f"{node['entity']}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    c = h["counts"]
    lines = [
        "---",
        "kind: person-resolution",
        f"axis: {h['axis']}",
        f"entity: {h['entity']}",
        "sealed: true",
        f"same_person: {json.dumps(h['same_person'])}",
        f"verdict: {json.dumps(h['verdict'])}",
        "---",
        "",
        f"# {h['display_name']} - cross-corpus resolution handle (sealed, refs-only)",
        "",
        "<!-- COMMITTED but REFS-ONLY (soul_corpus/sealed/): the tools never inline this; it carries",
        "real identity (the cross-corpus key) and public join evidence ONLY. The chat-derived profile",
        "is LOCAL (archive/soul_dump/_shard/resolved/, gitignored). Content-free by construction",
        "(soul_resolve._safe_handle) - no sealed member, no sealed text, ever reaches this file. -->",
        "",
        f"**Aliases (the resolution key):** {', '.join(h['aliases']) or '-'}",
        "",
        "## Members (counts only)",
        "",
        f"- **sealed (soul-dump):** {c['sealed_chunks']} chunks across {c['sealed_sources']} source(s)",
        f"- **public:** {c['public_refs']} ref(s)",
        "",
        "## Public join evidence (public ↔ public, the same person on paper)",
        "",
    ]
    if h["public_join"]:
        for j in h["public_join"]:
            if isinstance(j, dict):
                key = j.get("arxiv") or j.get("key") or ""
                title = j.get("title", "")
                lines.append(f"- `{key}` — {title}".rstrip(" —"))
            else:
                lines.append(f"- {j}")
    else:
        lines.append("- (none recorded)")
    lines += [
        "",
        "## Verdict",
        "",
        f"- **same person across corpora:** {json.dumps(h['same_person'])}"
        + (f" (confidence {h['confidence']})" if h["confidence"] is not None else ""),
        f"- **adjudication (builder≠judge):** {json.dumps(h['verdict'])}",
    ]
    if h["negative_controls"]:
        lines += ["", "## Negative controls (must NOT merge)", ""]
        lines += [f"- {n}" for n in h["negative_controls"]]
    if h["public_refs"]:
        lines += ["", "## Public refs", ""]
        lines += [f"- [[{r}]]" for r in h["public_refs"]]
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# verify - the link closes (sampled, never O(N^2))
# ---------------------------------------------------------------------------

def local_faithfulness(repo_root: Path | str, node: dict[str, Any], k: int = 3) -> dict[str, Any]:
    """Sample the node's sealed members and confirm each reconstructs (exact char range recovered),
    so the inter-grade link points at real, recoverable leaves. O(k), not O(N^2). Deterministic
    sampling (first / middle / last), no RNG. The STRUCTURAL half of the gate; the semantic half
    (does the lifted handle capture its members) is the judge's verdict, attached separately."""
    repo_root = Path(repo_root)
    shards = soul_shard.load_local_index(repo_root)
    by_id = {s["id"]: s for s in shards}
    ids = [m["id"] for m in node["members"]["sealed"]]
    checked = recovered = 0
    bad: list[str] = []
    if ids:
        for p in sorted({0, len(ids) // 2, len(ids) - 1})[:k]:
            cid = ids[p]
            checked += 1
            sh = by_id.get(cid)
            if sh and sh["end"] <= sh["start"]:
                recovered += 1
                continue
            text = soul_shard.reconstruct(repo_root, cid, shards)
            if sh and text and len(text) == sh["n_chars"]:
                recovered += 1
            else:
                bad.append(cid)
    return {"pass": not bad, "sealed_members": len(ids), "sampled": checked,
            "recovered": recovered, "bad": bad[:10]}


# ---------------------------------------------------------------------------
# entry - the mechanical halves (gather + persist skeleton + gate) for a spec file
# ---------------------------------------------------------------------------

def default_repo_root() -> Path:
    return source_tree()


def main(argv: list[str]) -> int:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    if not argv:
        print("usage: soul_resolve <entity_spec.json>  (gathers + persists skeleton + gate; the "
              "resolution is attached by the sealed wave, not here)")
        return 2
    root = default_repo_root()
    entity = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    node = gather(root, entity)
    write_local(root, node)
    write_handle(root, node)
    gate = local_faithfulness(root, node)
    print(json.dumps({"counts": node["counts"], "gate": gate}, ensure_ascii=False, indent=2))
    return 0 if gate["pass"] else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
