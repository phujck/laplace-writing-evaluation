"""stage_tranche.py - the seal-safe staging step of the scaled soul pour (Stage 4).

The orchestrator NEVER reads raw soul content. This script runs as a SUBPROCESS:
it loads the gitignored shard index, selects a tranche structurally, reconstructs
each chosen chunk's source range via ``soul_shard.reconstruct``, and writes the
reconstructed text to a GITIGNORED sealed file that the Haiku distiller subs Read.
It prints ONLY seal-safe stats - per-source counts, categories, and the his/other
turn split parsed from the chunk labels. Never a word of message content.

This is the durable, resumable staging machine for the multi-session pour (the
prior calibration staged inline; this commits the step so the way-back holds).

Usage:
  python scripts/stage_tranche.py survey
  python scripts/stage_tranche.py survey --category claude_chats
  python scripts/stage_tranche.py stage --sources alicia,guy_skinner --out _shard/tranche2_stage.json
  python scripts/stage_tranche.py stage --sources <basename> --max-chunks 40 --out ...
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from laplace.engine import soul_shard  # noqa: E402

_GO = re.compile(r"g(\d+)o(\d+)")


def _split(label: str) -> tuple[int, int]:
    """Parse the his/other turn split from a dialogue chunk label; (0, 0) if absent."""
    m = _GO.search(label or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _basename(source: str) -> str:
    return source.rsplit("/", 1)[-1]


def _content_chunks(shards: list[dict]) -> list[dict]:
    """Only real text chunks (drop asset/dup/header name-only nodes)."""
    out = []
    for s in shards:
        if s["end"] <= s["start"]:
            continue
        if s["id"].endswith("#asset") or s["id"].endswith("#dup"):
            continue
        out.append(s)
    return out


def survey(repo_root: Path, category: str | None) -> int:
    shards = _content_chunks(soul_shard.load_local_index(repo_root))
    by_src: dict[str, dict] = defaultdict(lambda: {"chunks": 0, "g": 0, "o": 0, "chars": 0, "category": ""})
    for s in shards:
        if category and s["category"] != category:
            continue
        rec = by_src[s["source"]]
        g, o = _split(s["label"])
        rec["chunks"] += 1
        rec["g"] += g
        rec["o"] += o
        rec["chars"] += s["n_chars"]
        rec["category"] = s["category"]
    rows = sorted(by_src.items(), key=lambda kv: (kv[1]["category"], -kv[1]["g"], -kv[1]["chunks"]))
    cat_tot: dict[str, dict] = defaultdict(lambda: {"sources": 0, "chunks": 0, "g": 0, "o": 0})
    print(f"{'category':<16} {'chunks':>7} {'his':>6} {'other':>6}  source")
    print("-" * 72)
    for src, r in rows:
        ct = cat_tot[r["category"]]
        ct["sources"] += 1
        ct["chunks"] += r["chunks"]
        ct["g"] += r["g"]
        ct["o"] += r["o"]
        print(f"{r['category']:<16} {r['chunks']:>7} {r['g']:>6} {r['o']:>6}  {_basename(src)}")
    print("-" * 72)
    print("TOTALS by category (sources / chunks / his-turns / other-turns):")
    for cat, ct in sorted(cat_tot.items(), key=lambda kv: -kv[1]["chunks"]):
        print(f"  {cat:<16} {ct['sources']:>4} src  {ct['chunks']:>6} chunks  "
              f"{ct['g']:>6} his  {ct['o']:>6} other")
    return 0


def stage(repo_root: Path, sources: list[str], ids: list[str], category: str | None,
          max_chunks: int, out: str) -> int:
    shards = _content_chunks(soul_shard.load_local_index(repo_root))
    selected: list[dict] = []
    if ids:
        wanted = set(ids)
        selected = [s for s in shards if s["id"] in wanted]
    else:
        per_src: dict[str, int] = defaultdict(int)
        srcs_lower = [x.lower() for x in sources]
        for s in shards:
            if category and s["category"] != category:
                continue
            base = _basename(s["source"]).lower()
            if sources and not any(x in base for x in srcs_lower):
                continue
            if max_chunks and per_src[s["source"]] >= max_chunks:
                continue
            per_src[s["source"]] += 1
            selected.append(s)
    if not selected:
        print("no chunks matched the selection", file=sys.stderr)
        return 2
    # out is a DIRECTORY: one sealed .txt per shard (each agent reads only its own window)
    # plus a seal-safe _manifest.json (ids / labels / person only - NO content).
    out_dir = repo_root / "archive" / "soul_dump" / out if not out.startswith("archive") else repo_root / out
    out_dir.mkdir(parents=True, exist_ok=True)
    # content-hash identity across EVERY existing _shard/*/ output dir (the store's own law,
    # WO-20260820-chat-shard-dedup): a chunk already materialized anywhere collapses to that one
    # canonical path rather than duplicating bytes under this second directory.
    canonical = soul_shard.materialized_index(repo_root)
    manifest_rows = []
    g_tot = o_tot = chars = 0
    src_set = set()
    n_dupe = 0
    for s in selected:
        text = soul_shard.reconstruct(repo_root, s["id"], shards)
        if not text:
            continue
        g, o = _split(s["label"])
        g_tot += g
        o_tot += o
        chars += len(text)
        src_set.add(s["source"])
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", s["id"])
        h = soul_shard.content_hash(text)
        canon = canonical.get(h)
        if canon is not None:
            n_dupe += 1
            manifest_rows.append({"id": s["id"], "file": None, "duplicate_of": canon,
                                  "person": _basename(s["source"]), "category": s["category"],
                                  "label": s["label"], "n_chars": len(text)})
            continue
        rel = str((out_dir / f"{safe}.txt").relative_to(repo_root)).replace("\\", "/")
        (out_dir / f"{safe}.txt").write_text(text, encoding="utf-8")
        canonical[h] = rel
        manifest_rows.append({"id": s["id"], "file": f"{safe}.txt", "person": _basename(s["source"]),
                              "category": s["category"], "label": s["label"], "n_chars": len(text)})
    (out_dir / "_manifest.json").write_text(json.dumps(manifest_rows, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    # seal-safe stats ONLY
    n_written = len(manifest_rows) - n_dupe
    print(f"STAGED {n_written} shards / {len(src_set)} sources -> {out_dir.relative_to(repo_root)}/"
          f" ({n_dupe} identical-content chunks already materialized elsewhere, collapsed to "
          f"their canonical path - not duplicated)")
    print(f"  his-turns {g_tot} | other-turns {o_tot} | total chars {chars:,}")
    print(f"  sources: {', '.join(sorted(_basename(x) for x in src_set))}")
    return 0


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("survey")
    sv.add_argument("--category", default=None)
    st = sub.add_parser("stage")
    st.add_argument("--sources", default="")
    st.add_argument("--ids", default="")
    st.add_argument("--category", default=None)
    st.add_argument("--max-chunks", type=int, default=0)
    st.add_argument("--out", required=True)
    a = p.parse_args(argv)
    repo_root = soul_shard.default_repo_root()
    if a.cmd == "survey":
        return survey(repo_root, a.category)
    sources = [x.strip() for x in a.sources.split(",") if x.strip()]
    ids = [x.strip() for x in a.ids.split(",") if x.strip()]
    return stage(repo_root, sources, ids, a.category, a.max_chunks, a.out)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
