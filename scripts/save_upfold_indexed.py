"""Save an indexed upfold (wf_upfold_only v2) into the shard: map integer indices -> ladder
ids MECHANICALLY, verify the partition (every index exactly once), replace the shard's
upfold. The model wrote cluster structure; the mechanics own the identifiers.

Usage: save_upfold_indexed.py <workflow-output.json> <key>
"""
import io
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
SD = ROOT / "collaborator_corpus" / "_structural"


def main(out_path, key):
    raw = json.loads(Path(out_path).read_text(encoding="utf-8"))
    up = raw["result"]["upfold"]
    shard_path = SD / f"{key}.json"
    shard = json.loads(shard_path.read_text(encoding="utf-8"))
    ids = [l["id"] for l in shard["ladders"]]
    n = len(ids)

    counts = Counter(i for g in up["program"] for i in g["papers"])
    bad = [i for i in counts if not (isinstance(i, int) and 0 <= i < n)]
    dupes = sorted(i for i, c in counts.items() if c > 1 and i not in bad)
    missing = sorted(set(range(n)) - set(counts))
    print(f"partition check: {sum(counts.values())} assignments over {n} papers; "
          f"out-of-range {len(bad)}, duplicated {len(dupes)}, missing {len(missing)}")
    if bad:
        print("  OUT OF RANGE:", bad[:20])
        return 1
    if dupes:
        print("  duplicated indices (kept in FIRST generator only):", dupes[:20])
        seen = set()
        for g in up["program"]:
            kept = []
            for i in g["papers"]:
                if i in seen:
                    continue
                seen.add(i)
                kept.append(i)
            g["papers"] = kept
    if missing:
        print("  missing indices recorded as uncovered grit:", missing[:30])

    mapped = {"program": [{"generator": g["generator"], "why": g["why"],
                           "papers": [ids[i] for i in g["papers"]]}
                          for g in up["program"]],
              "technique_clusters": [{"technique": t["technique"],
                                      "papers": [ids[i] for i in t["papers"]
                                                 if isinstance(i, int) and 0 <= i < n]}
                                     for t in up.get("technique_clusters", [])],
              "note": up.get("note", "")}
    if missing:
        mapped["uncovered"] = [ids[i] for i in missing]
    shard["upfold"] = mapped
    shard["_provenance"] = (shard.get("_provenance", "") +
                            " | upfold REPLACED 2026-06-11 by wf_upfold_only v2 (indexed, "
                            "ids mapped mechanically; v1 4-gen upfold was too coarse to descend)")
    shard_path.write_text(json.dumps(shard, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{key}: upfold replaced - {len(mapped['program'])} generators")
    for g in mapped["program"]:
        print(f"  [{len(g['papers'])} papers] {g['generator'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
