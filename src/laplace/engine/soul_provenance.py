"""soul_provenance.py - the locator instrument over the folded soul-corpus (the provenance floor).

The locator law (his, 2026-06-10): every item in every field of a folded result carries its
substrate locator(s), so the cross-link (``keeper_ring.coupling``) is READ OFF shared substrate,
never re-derived. The law's upstream half lives in ``soul_dream._PROVENANCE_RULE`` (the brief every
sealed fold/re-fold runs under); this module is the MECHANICAL half:

  * it MEASURES locator coverage per entity x field - the acceptance gate for the law, and a
    phi-style instrument (watched, not imposed: coverage rises as the cycle re-folds the world,
    nothing is patched to make the number move);
  * it PARSES locators into window tokens and exposes them as ``keeper_ring`` reach, so coupling
    between two soul entities is a read-off of shared substrate windows;
  * it never WRITES a locator. Attribution is a semantic act and belongs to the sealed wave at
    fold time - a mechanical matcher over paraphrased syntheses would risk CONFABULATED PROVENANCE
    (a wrong pointer is worse than a missing one). The backfill of the existing layer is the cycle
    re-folding under the locator law, not a bespoke matcher (there is one thing).

Seal: walks the gitignored folded layer in-process; the rich report (entity names + couplings)
stays in the sealed tree (``_provenance_report.json``); ``summary()``/the CLI return are
content-free - counts and rates only, never a name or a fact.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import json
from pathlib import Path
from typing import Any

from laplace.engine import keeper_ring
from laplace.engine.soul_dream import SHARD, _folded_dirs

# The fields the locator law covers. ``history`` already carries locators (the floor that never
# dropped them); ``voice``/``generator`` are the bare-string gap the law closes; ``relations``/
# ``conjectural`` ride the same rule.
LOCATOR_FIELDS = ("voice", "history", "relations", "generator", "conjectural")

REPORT_LOCAL = f"{SHARD}/_provenance_report.json"   # sealed, gitignored - the rich view


# ---------------------------------------------------------------------------
# enumerate entity-shaped files - structure + locators only, no content judgement
# ---------------------------------------------------------------------------

def _candidate_files(repo_root: Path) -> list[Path]:
    """Entity-shaped JSON candidates: the apexes at the shard top level, every folded tranche's
    entity files, and each tranche's ``_xworld`` cross-resolves. Raw slice/window shards are not
    walked (they are substrate, not folded results)."""
    repo_root = Path(repo_root)
    shard = repo_root / SHARD
    if not shard.is_dir():
        return []
    out = list(shard.glob("*.json"))
    for folded in _folded_dirs(repo_root):
        out += folded.glob("*.json")
        if (folded / "_xworld").is_dir():
            out += (folded / "_xworld").glob("*.json")
    return sorted(set(out))


def iter_entities(repo_root: Path | str) -> list[tuple[Path, dict[str, Any]]]:
    """Load every folded ENTITY: a dict bearing ``name`` and at least one locator-law field.
    Plans, maps, reports and malformed files fall out by shape, not by name-listing."""
    out: list[tuple[Path, dict[str, Any]]] = []
    for path in _candidate_files(Path(repo_root)):
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("name") and any(k in data for k in LOCATOR_FIELDS):
            out.append((path, data))
    return out


# entity lookup by stem - mtime-stamped cache so fold-time item embedding never re-walks the
# shard per item (one walk fills every stem; ~400 item embeds then cost ~400 dict hits).
_BY_STEM_CACHE: dict[str, dict[str, Any]] = {}


def shard_stamp(repo_root: Path | str) -> tuple[int, int]:
    """``(candidate count, newest mtime_ns)`` over the folded-entity shard - names and stat()s
    only, never a content read. This is the invalidation key ``entities_by_stem`` has always
    used for its own per-process cache, lifted to a function because a second cache now needs
    the same stamp: ``embed_router.basis`` memoises the whole embedding basis, and the item text
    this module serves is the one ``node_text`` input that lives on disk outside both ``net`` and
    the vector cache. 53 files / ~1 ms measured, so it can ride a per-call memo key."""
    files = _candidate_files(Path(repo_root))
    return (len(files), max((f.stat().st_mtime_ns for f in files), default=0))


def entities_by_stem(repo_root: Path | str) -> dict[str, tuple[Path, dict[str, Any]]]:
    """``stem -> (path, folded entity)`` for every entity-shaped file, cached on the candidate
    set's (count, max-mtime) stamp - a re-fold invalidates, an unchanged shard never re-reads."""
    repo_root = Path(repo_root)
    key = str(repo_root.resolve())
    stamp = shard_stamp(repo_root)
    cur = _BY_STEM_CACHE.get(key)
    if cur and cur["stamp"] == stamp:
        return cur["by_stem"]
    by_stem = {p.stem: (p, d) for p, d in iter_entities(repo_root)}
    _BY_STEM_CACHE[key] = {"stamp": stamp, "by_stem": by_stem}
    return by_stem


# the head key per routable field (the profile fields - what person recall descends into)
ITEM_FIELDS: dict[str, str] = {"voice": "trait", "history": "event", "relations": "who"}


def item_of(repo_root: Path | str, stem: str, field: str, idx: int) -> dict[str, Any] | None:
    """One field item of one folded entity, by position - the leaf the item-node serves."""
    ent = entities_by_stem(repo_root).get(stem)
    if ent is None or field not in ITEM_FIELDS:
        return None
    items = ent[1].get(field)
    if not isinstance(items, list) or not (0 <= idx < len(items)):
        return None
    it = items[idx]
    return it if isinstance(it, dict) else {"note": str(it)}


def item_text(repo_root: Path | str, stem: str, field: str, idx: int) -> str:
    """The item's text for FOLD-TIME embedding ONLY: name + field + head + note. The result is
    hashed into the gitignored vector cache and never serialized anywhere else - the same posture
    as the entity-name fix (identity and now meaning ride the LOCAL geometry; the commit/return
    boundary still carries only content-free handles)."""
    it = item_of(repo_root, stem, field, idx)
    if it is None:
        return ""
    head = str(it.get(ITEM_FIELDS.get(field, "")) or "").strip()
    note = str(it.get("note") or "").strip()
    name = stem.replace("_", " ").replace("-", " ")
    return " | ".join(p for p in (name, field, head, note) if p)


# ---------------------------------------------------------------------------
# the people census - the rewiring sweep's gate (content-free: names + masses)
# ---------------------------------------------------------------------------

CHAT_LOGS = "archive/soul_dump/raw/chat_logs"


def people_census(repo_root: Path | str) -> dict[str, Any]:
    """Every person-shaped SOURCE mass vs the promoted entities - names, sizes and counts ONLY
    (names are identity, the handle; content never rises). The sweep's gate: the author reads
    this list and rules the promotion ORDER (the initial wiring was too conservative and wired
    out of the order one would expect - his diagnosis, 2026-06-11)."""
    repo_root = Path(repo_root)
    promoted = entities_by_stem(repo_root)

    def _norm(name: str) -> str:
        return name.lower().replace(" ", "_").replace("-", "_")

    by_norm = {_norm(stem): stem for stem in promoted}
    sources: list[dict[str, Any]] = []
    chat_root = repo_root / CHAT_LOGS
    if chat_root.is_dir():
        for d in sorted(chat_root.iterdir()):
            if not d.is_dir():
                continue
            files = [f for f in d.rglob("*") if f.is_file()]
            stem = by_norm.get(_norm(d.name))
            ent = promoted.get(stem) if stem else None
            n_items = (sum(len(ent[1].get(f) or []) for f in ITEM_FIELDS) if ent else 0)
            sources.append({"source": d.name, "kind": "chat",
                            "files": len(files),
                            "kb": sum(f.stat().st_size for f in files) // 1024,
                            "promoted": stem is not None,
                            "stem": stem, "items": n_items})
    chat_norms = {_norm(s["source"]) for s in sources}
    orphans = [{"source": stem, "kind": "entity-only", "files": 0, "kb": 0,
                "promoted": True, "stem": stem,
                "items": sum(len(d.get(f) or []) for f in ITEM_FIELDS)}
               for stem, (_p, d) in sorted(promoted.items())
               if _norm(stem) not in chat_norms and not stem.startswith("_")]
    rows = sorted(sources, key=lambda s: -s["kb"]) + orphans
    return {"rows": rows,
            "n_sources": len(sources),
            "n_promoted": sum(1 for r in rows if r["promoted"]),
            "n_missing": sum(1 for r in sources if not r["promoted"]),
            "note": "names + masses only (identity is the handle); the promotion order is the "
                    "author's ruling - the sweep folds in HIS order, sealed subs, one entity each"}


# ---------------------------------------------------------------------------
# locator parsing - the read-off's vocabulary
# ---------------------------------------------------------------------------

def item_locator(item: Any) -> str | None:
    """The locator a field item carries, or None. A bare string is the pre-law shape (no locator);
    a dict carries one under ``locator`` (null/empty = declared-null, still no locator)."""
    if isinstance(item, dict):
        loc = item.get("locator")
        if isinstance(loc, str) and loc.strip():
            return loc
    return None


def locator_tokens(locator: str) -> set[str]:
    """Window tokens from a locator string - ``'file_5.txt:101-102, 282:100-114'`` names windows
    ``{'file_5.txt', '282'}``. The token is the slice/window id (the part before the line-range);
    two entities sharing a token share substrate, which is exactly what coupling counts."""
    out: set[str] = set()
    for part in locator.split(","):
        tok = part.strip().split(":")[0].strip()
        if tok:
            out.add(tok)
    return out


# ---------------------------------------------------------------------------
# coverage - the acceptance gate (and the instrument's needle)
# ---------------------------------------------------------------------------

def field_coverage(entity: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Per-field ``{n, with_locator}`` for one entity - counts only."""
    out: dict[str, dict[str, int]] = {}
    for field in LOCATOR_FIELDS:
        items = entity.get(field)
        if not isinstance(items, list):
            continue
        n_loc = sum(1 for it in items if item_locator(it))
        out[field] = {"n": len(items), "with_locator": n_loc}
    return out


def coverage(repo_root: Path | str) -> dict[str, Any]:
    """Locator coverage across the folded layer: per-file (rich, for the sealed report) and the
    per-field totals (content-free). The rate per field is the law's needle - it rises only when
    the cycle re-folds under the law."""
    files: dict[str, dict[str, dict[str, int]]] = {}
    totals: dict[str, dict[str, int]] = {f: {"n": 0, "with_locator": 0} for f in LOCATOR_FIELDS}
    for path, entity in iter_entities(repo_root):
        cov = field_coverage(entity)
        files[path.stem] = cov
        for field, c in cov.items():
            totals[field]["n"] += c["n"]
            totals[field]["with_locator"] += c["with_locator"]
    rates = {f: (round(t["with_locator"] / t["n"], 3) if t["n"] else None)
             for f, t in totals.items()}
    return {"files": files, "totals": totals, "rates": rates,
            "n_entities": len(files)}


# ---------------------------------------------------------------------------
# reach + coupling - the read-off (never re-derived)
# ---------------------------------------------------------------------------

def entity_reach(repo_root: Path | str) -> dict[str, set[str]]:
    """``entity-file-stem -> the set of substrate window tokens its locators name`` - the soul
    conjugate of ``keeper_ring.build_reach``'s edge-target reach. Feed straight into
    ``keeper_ring.coupling`` / ``shared_substrate``: the cross-link is |reach(a) & reach(b)|."""
    reach: dict[str, set[str]] = {}
    for path, entity in iter_entities(repo_root):
        toks: set[str] = set()
        for field in LOCATOR_FIELDS:
            items = entity.get(field)
            if not isinstance(items, list):
                continue
            for it in items:
                loc = item_locator(it)
                if loc:
                    toks |= locator_tokens(loc)
        reach[path.stem] = toks
    return reach


def top_couplings(reach: dict[str, set[str]], k: int = 20) -> list[tuple[int, str, str]]:
    """The strongest entity-entity couplings by shared substrate windows, descending - the
    read-off ``keeper_ring.coupling`` over the soul reach. Zero-couplings dropped."""
    ids = sorted(reach)
    pairs: list[tuple[int, str, str]] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            c = keeper_ring.coupling(reach, a, b)
            if c > 0:
                pairs.append((c, a, b))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))
    return pairs[:k]


# ---------------------------------------------------------------------------
# mechanical reconstruction - render a folded entity as a profile (NO model)
# ---------------------------------------------------------------------------

_PROFILE_FIELDS = (("voice", "Voice", "trait"), ("history", "History", "event"),
                   ("relations", "Relations", "who"))


def render_entity_profile(data: dict[str, Any]) -> str:
    """Reconstruct an entity profile MECHANICALLY - a deterministic render of the already-folded
    fields, no model, no generation (his correction, 2026-06-10: reconstruction is mechanical;
    the intelligence is paid ONCE at fold time, reading back is assembly, not re-derivation - a
    model per reconstruction would prove the network holds nothing). Every line traces to its
    source locator, so the render cannot confabulate beyond the fold. Pure; the caller decides
    where it goes (the scanner serves it to the author's browser - never the orchestrator)."""
    name = str(data.get("name") or "(unnamed)")
    out = [f"# {name}", ""]
    summary = str(data.get("summary") or "").strip()
    if summary:
        out += [summary, ""]
    out += ["_Mechanically reconstructed from the folded entity - every line traces to its source "
            "chunk; no model, no generation._", ""]
    for field, heading, key in _PROFILE_FIELDS:
        items = data.get(field)
        if not isinstance(items, list) or not items:
            continue
        out.append(f"## {heading}")
        for it in items:
            if not isinstance(it, dict):
                continue
            head = str(it.get(key) or "").strip()
            if not head:
                continue
            note = str(it.get("note") or "").strip()
            loc = item_locator(it)
            bullet = f"- {head}" + (f" - {note}" if note else "") + (f"  _({loc})_" if loc else "")
            out.append(bullet)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------
# report (rich, sealed) + summary (content-free)
# ---------------------------------------------------------------------------

def write_report(repo_root: Path | str) -> Path:
    """Persist the RICH provenance view (per-entity coverage + named couplings) into the sealed
    gitignored tree, beside the plan the wave reads. Never committed, never returned."""
    repo_root = Path(repo_root)
    cov = coverage(repo_root)
    reach = entity_reach(repo_root)
    rich = {
        **cov,
        "couplings": [{"shared": c, "a": a, "b": b} for c, a, b in top_couplings(reach)],
    }
    out = repo_root / REPORT_LOCAL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rich, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def summary(repo_root: Path | str) -> dict[str, Any]:
    """The content-free projection: counts and rates only - what may ride into a context or a
    commit. The needle to watch: ``rates`` per field, and how many couplings are nonzero."""
    cov = coverage(repo_root)
    reach = entity_reach(repo_root)
    pairs = top_couplings(reach, k=10_000)
    return {
        "n_entities": cov["n_entities"],
        "totals": cov["totals"],
        "rates": cov["rates"],
        "n_nonzero_couplings": len(pairs),
        "max_coupling": pairs[0][0] if pairs else 0,
    }


def main(argv: list[str] | None = None) -> int:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    args = argv if argv is not None else sys.argv[1:]
    positional = [a for a in args if not a.startswith("--")]
    root = Path(positional[0]) if positional else source_tree()
    if "--report" in args:
        write_report(root)
    print(json.dumps(summary(root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
