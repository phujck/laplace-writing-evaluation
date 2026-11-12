"""Build the self-record works file (mechanical, no model): each session handoff becomes
one entry {id, title, abstract, year} - the same substrate shape the structural shard
consumes for papers, so the SAME wf_structural_shard.mjs runs on the self-record (one
operator; sessions are the papers of the build programme). The abstract = the handoff's
top (arc + shipped headlines), where aim/approach/moves/outcomes live densest.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "archive" / "self_record" / "_structural"
CAP = 2400

entries = []
files = sorted(ROOT.glob("SESSION_HANDOFF_*.md")) + sorted((ROOT / "src" / "laplace").glob("SESSION_HANDOFF_*.md"))
for f in files:
    text = f.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^#\s*(.+)$", text, re.MULTILINE)
    title = (m.group(1).strip() if m else f.stem)
    ym = re.search(r"(\d{4})-(\d{2})-(\d{2})", f.name)
    entries.append({
        "id": f.stem,
        "title": title,
        "abstract": text[:CAP],
        "year": ym.group(0) if ym else "",
    })

OUT.mkdir(parents=True, exist_ok=True)
out = OUT / "self_record_works.json"
out.write_text(json.dumps(entries, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"{len(entries)} session entries -> {out.relative_to(ROOT)}")
