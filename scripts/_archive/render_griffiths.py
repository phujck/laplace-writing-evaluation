"""The direct mechanical render of David Griffiths - the same assembly the node view
serves: entity fields read from the sealed local tree, ordered, verbatim. No model."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

from laplace.engine import soul_provenance

root = Path(__file__).resolve().parent.parent
by_stem = soul_provenance.entities_by_stem(root)
stem, data = None, None
for s, d in by_stem.items():
    if "griffiths" in s.lower():
        stem, data = s, d
        break
if not data:
    print("entity not found in sealed tree")
    sys.exit(1)
path, fields = data
print(f"ENTITY: {stem}  (sealed local file: {path})")
for field in soul_provenance.ITEM_FIELDS:
    items = fields.get(field)
    if not isinstance(items, list):
        continue
    print(f"\n[{field}] ({len(items)})")
    for it in items:
        if isinstance(it, dict):
            txt = it.get("statement") or it.get("text") or it.get("claim") or str(it)
            loc = soul_provenance.item_locator(it) or ""
            print(f"  - {txt}" + (f"   <{loc}>" if loc else ""))
        else:
            print(f"  - {it}")
