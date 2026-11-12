"""Wave-2b preflight: resolve each collaborator's display name from the coauth/works files."""
import io
import json
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

for k in ("alanissila", "balanov", "booth", "jacobs", "totero"):
    co = json.load(open(f"collaborator_corpus/_raw/{k}_coauth.json", encoding="utf-8"))
    print(f"{k}: coauth is {type(co).__name__}", end=" | ")
    if isinstance(co, list) and co:
        print("first entry:", json.dumps(co[0], ensure_ascii=False)[:160])
    works = json.load(open(f"collaborator_corpus/_raw/{k}_works.json", encoding="utf-8"))
    names = Counter()
    for w in works[:60]:
        for a in w.get("authorships") or []:
            n = (a.get("author") or {}).get("display_name")
            if n:
                names[n] += 1
    print(f"   top authors: {names.most_common(3)}")
