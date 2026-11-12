"""Build the soul-dump's vectorised embedded structure for remote reconstruction.

His call (2026-06-15, F-NEW / F24 / F27 resolved): the soul dump's *folded distillates* +
their vectors travel to the (private, single-access) repo so remote containers reconstruct the
family vectorially the way local does. The *raw verbatim* dump (archive/soul_dump/raw/ - chats,
PDFs, zips) stays gitignored; only the distilled folds + embeddings rise.

What it does:
  1. Collects the soul-dump DISTILLATE files (entity folds, chunk folds, traits, crosslinks,
     apex) - never the raw, never the processing-log junk.
  2. Flattens each into self-describing NODES (a person's trait, a history fact, a relation,
     an apex group/theme) with a stable id + source + content-hash.
  3. Embeds each node's payload with the vendored local model (embed_router backend).
  4. Writes the travelling store to soul_vectors/ : nodes.jsonl (payload + 384-float vec),
     manifest.json (provenance + seal note + per-source counts), and a README.

Re-runnable anywhere the distillates + the model are present. Output is content-addressed, so
re-running is idempotent. Run:  python scripts/build_soul_vectors.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.representation import embed_router as ER  # noqa: E402

SHARD = ROOT / "archive" / "soul_dump" / "_shard"
OUT = ROOT / "soul_vectors"
MAX_PAYLOAD = 1600  # truncate very long leaves before embed/store (bounds artifact size)

# ---- node extraction -------------------------------------------------------

def _h(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()

def _clip(s: str) -> str:
    s = " ".join(str(s).split())
    return s[:MAX_PAYLOAD]

def _node(nid, kind, source, payload, person=None, grade=None):
    payload = _clip(payload)
    if len(payload) < 8:
        return None
    n = {"id": nid, "kind": kind, "source": source, "payload": payload, "h": _h(payload)}
    if person:
        n["person"] = person
    if grade is not None:
        n["grade"] = grade
    return n

def from_entity_fold(obj, src):
    """sweep_folded/*.json : {name, summary, voice:[{trait,note}], history:[{event}], relations:[{who,note}]}"""
    out = []
    name = obj.get("name") or Path(src).stem
    if obj.get("summary"):
        out.append(_node(f"{src}#summary", "person.summary", src, f"{name} — {obj['summary']}", person=name, grade=1))
    for i, v in enumerate(obj.get("voice", []) or []):
        if isinstance(v, dict):
            t = v.get("trait", ""); note = v.get("note", "")
            txt = f"{name}: {t}" + (f" — {note}" if note else "")
        else:
            txt = f"{name}: {v}"
        out.append(_node(f"{src}#voice{i}", "person.voice", src, txt, person=name, grade=2))
    for i, e in enumerate(obj.get("history", []) or []):
        ev = e.get("event") or e.get("fact") if isinstance(e, dict) else str(e)
        if ev:
            out.append(_node(f"{src}#hist{i}", "person.history", src, f"{name} — {ev}", person=name, grade=2))
    for i, r in enumerate(obj.get("relations", []) or []):
        if isinstance(r, dict):
            who = r.get("who", ""); note = r.get("note", "")
            txt = f"{name} ↔ {who}: {note}"
        else:
            txt = f"{name} ↔ {r}"
        out.append(_node(f"{src}#rel{i}", "person.relation", src, txt, person=name, grade=2))
    return [n for n in out if n]

def from_atom_list(atoms, src, person):
    """chunk folds: list of atoms (or {gerard_atoms:[...]}), each {voice:[...], history:[{fact}]}."""
    out = []
    for ai, atom in enumerate(atoms):
        if not isinstance(atom, dict):
            continue
        for j, v in enumerate(atom.get("voice", []) or []):
            out.append(_node(f"{src}#a{ai}v{j}", "atom.voice", src, f"{person}: {v}", person=person, grade=3))
        for j, e in enumerate(atom.get("history", []) or []):
            ev = e.get("fact") or e.get("event") if isinstance(e, dict) else str(e)
            if ev:
                out.append(_node(f"{src}#a{ai}h{j}", "atom.history", src, f"{person} — {ev}", person=person, grade=3))
        for j, r in enumerate(atom.get("relations", []) or []):
            if isinstance(r, dict):
                txt = f"{r.get('who','')}: {r.get('note','')}"
            else:
                txt = str(r)
            out.append(_node(f"{src}#a{ai}r{j}", "atom.relation", src, txt, person=person, grade=3))
    return [n for n in out if n]

def from_apex(obj, src):
    out = []
    if obj.get("apex_essence"):
        out.append(_node(f"{src}#essence", "apex.essence", src, obj["apex_essence"], grade=0))
    for i, g in enumerate(obj.get("groups", []) or []):
        if isinstance(g, dict):
            mem = ", ".join(g.get("members", []) or [])
            txt = f"{g.get('name','')}: {g.get('essence','')} (members: {mem})"
            out.append(_node(f"{src}#group{i}", "apex.group", src, txt, grade=1))
    for i, t in enumerate(obj.get("emergent_themes", []) or []):
        out.append(_node(f"{src}#theme{i}", "apex.theme", src, str(t), grade=1))
    return [n for n in out if n]

def _strings(obj, prefix=""):
    """Generic deep string-leaf walk for unknown distillate schemas (traits, crosslinks)."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += _strings(v, f"{prefix}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _strings(v, f"{prefix}[{i}]")
    elif isinstance(obj, str) and len(obj.strip()) >= 12:
        out.append((prefix, obj))
    return out

def from_generic(obj, src, kind, grade):
    out = []
    label = Path(src).stem.replace("_", " ").replace("-", " ")
    for path, s in _strings(obj):
        out.append(_node(f"{src}#{path}", kind, src, f"[{label}] {s}", grade=grade))
    return [n for n in out if n]

# ---- collection ------------------------------------------------------------

def collect():
    nodes = []
    rel = lambda p: str(p.relative_to(ROOT)).replace("\\", "/")

    # entity folds (people) — sweep_folded top-level + _gerard subset (content-hash dedups dupes)
    for p in sorted((SHARD / "sweep_folded").rglob("*.json")):
        try:
            o = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(o, dict) and ("voice" in o or "summary" in o or "history" in o):
            nodes += from_entity_fold(o, rel(p))
        elif isinstance(o, list):
            nodes += from_atom_list(o, rel(p), Path(p).stem)

    # chunk folds (distilled per-conversation atoms)
    for base in ("scaled_tranche1_folded", "scaled_tranche2_folded"):
        for p in sorted((SHARD / base).rglob("*.json")):
            if p.name.startswith("_manifest"):
                continue
            try:
                o = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            person = Path(p).stem.split("_")[0].replace("chunk", "Gerard").title()
            if isinstance(o, dict) and "gerard_atoms" in o:
                nodes += from_atom_list(o["gerard_atoms"], rel(p), "Gerard")
            elif isinstance(o, list):
                nodes += from_atom_list(o, rel(p), person)
            elif isinstance(o, dict) and ("voice" in o or "summary" in o):
                nodes += from_entity_fold(o, rel(p))

    # apex (relational + gerard)
    for name in ("_APEX_RELATIONAL.json", "_GERARD_APEX.json"):
        p = SHARD / name
        if p.exists():
            try:
                nodes += from_apex(json.loads(p.read_text(encoding="utf-8")), rel(p))
            except Exception:
                pass

    # traits (welded/candidate self-traits distilled from the dump)
    for p in sorted((SHARD / "_traits").glob("*.json")):
        try:
            nodes += from_generic(json.loads(p.read_text(encoding="utf-8")), rel(p), "trait", 2)
        except Exception:
            pass

    # crosslinks (physics technique/concept bridges)
    for p in sorted((SHARD / "crosslink").glob("*.json")):
        try:
            nodes += from_generic(json.loads(p.read_text(encoding="utf-8")), rel(p), "crosslink", 2)
        except Exception:
            pass

    # resolved person nodes
    for p in sorted((SHARD / "resolved").glob("*.json")):
        try:
            o = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(o, dict) and ("voice" in o or "summary" in o):
                nodes += from_entity_fold(o, rel(p))
            else:
                nodes += from_generic(o, rel(p), "resolved", 1)
        except Exception:
            pass

    # dedup by content-hash (identical payloads across dup files collapse)
    seen, uniq = set(), []
    for n in nodes:
        if n["h"] in seen:
            continue
        seen.add(n["h"]); uniq.append(n)
    return uniq

# ---- main ------------------------------------------------------------------

def main():
    backend = ER.get_backend()
    bname = type(backend).__name__
    print(f"backend = {bname}")
    if bname != "FastEmbedBackend":
        print("REFUSING: not the vendored local model — vectors must be the real embedder, not the hash fallback.")
        return 1

    nodes = collect()
    print(f"collected {len(nodes)} distillate nodes")
    texts = [n["payload"] for n in nodes]
    vecs = []
    B = 256
    for i in range(0, len(texts), B):
        vecs.extend(backend.embed(texts[i:i + B]))
        print(f"  embedded {min(i + B, len(texts))}/{len(texts)}", end="\r")
    print()
    dim = len(vecs[0]) if vecs else 0
    for n, v in zip(nodes, vecs):
        n["v"] = [round(float(x), 6) for x in v]

    OUT.mkdir(exist_ok=True)
    with (OUT / "nodes.jsonl").open("w", encoding="utf-8") as f:
        for n in nodes:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")

    by_kind, by_source = {}, {}
    for n in nodes:
        by_kind[n["kind"]] = by_kind.get(n["kind"], 0) + 1
        by_source[n["source"]] = by_source.get(n["source"], 0) + 1
    manifest = {
        "what": "Vectorised embedded structure of the soul dump — folded distillates + local embeddings.",
        "built": "2026-06-15 (person-wake, his F-NEW/F24/F27 call: distillates travel, raw stays local)",
        "backend": f"fastembed:BAAI/bge-small-en-v1.5",
        "dim": dim,
        "n_nodes": len(nodes),
        "seal": "DISTILLATES ONLY. archive/soul_dump/raw/ (verbatim chats, PDFs, zips) is NOT here and stays gitignored. "
                "Payloads are folded summaries (voice/history/relations), not verbatim messages. Private repo, single-access; "
                "embedding-inversion caveat acknowledged by the author.",
        "by_kind": dict(sorted(by_kind.items(), key=lambda x: -x[1])),
        "n_sources": len(by_source),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT/'nodes.jsonl'} and manifest.json")
    print("by_kind:", manifest["by_kind"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
