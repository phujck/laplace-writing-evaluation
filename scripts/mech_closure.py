"""The MECHANICAL closure signal (his 2026-06-11: representations are conjugate - what needs
intelligence in the lexical rep is a dot product in the tokenised rep; transform to see the
efficient closure). For every node of a regraded ladder:

  cos_own  = cosine(stated essence, centroid of its OWN floor)        - does the label sit on its floor?
  margin   = cos_own - max cosine(stated essence, SIBLING floor centroids)  - or does it bleed?

Low cos_own ~ the lexical gate's DRIFT; low/negative margin ~ boundary bleed (the kvn/wave-operator
class). The expensive blind-recovery judges then fire ONLY on flagged nodes - the intelligent gate
becomes the second stage of a mechanical first pass. Same embedder as the live route (one rep,
view = mechanism).
"""
import json, re, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
SD = ROOT / "collaborator_corpus" / "_structural"
sys.path.insert(0, str(ROOT / "src"))

from laplace.representation import embed_router  # noqa: E402

def canon(pid):
    m = re.match(r"(W\d+)", pid.strip())
    return m.group(1) if m else pid.strip()

def unit(v):
    s = sum(x * x for x in v) ** 0.5
    return [x / s for x in v] if s else v

def centroid(vecs):
    if not vecs:
        return None
    n = len(vecs[0])
    return unit([sum(v[i] for v in vecs) / len(vecs) for i in range(n)])

def dot(a, b):
    return sum(x * y for x, y in zip(a, b))

KEY = sys.argv[1] if len(sys.argv) > 1 else "mccaul"
reg = json.loads((SD / f"{KEY}_regraded.json").read_text(encoding="utf-8"))
struct = json.loads((SD / f"{KEY}.json").read_text(encoding="utf-8"))
ladders = {}
for lad in struct["ladders"]:
    ladders.setdefault(canon(lad["id"]), lad)

def floor_text(cid):
    lad = ladders.get(cid)
    if not lad:
        return None
    techs = "; ".join(t.get("statement", t.get("name", "")) for t in lad.get("techniques", []))
    res = "; ".join(r.get("claim", "") for r in lad.get("results", []))
    return f"{lad.get('title','')}. {techs}. {res}"

backend = embed_router.get_backend()

# embed every paper floor once, then every stated essence
# (enrich-mode generators carry 'papers' directly - no rungs; their floor is the paper grade)
texts, keys = [], []
for g in reg["generators"]:
    for r in g.get("rungs") or []:
        for p in r["papers"]:
            ft = floor_text(p)
            if ft and ("paper", p) not in keys:
                keys.append(("paper", p)); texts.append(ft)
        keys.append(("rung", f"{g['label']}|{r['name']}")); texts.append(r["essence"])
    for p in g.get("papers") or []:
        ft = floor_text(p)
        if ft and ("paper", p) not in keys:
            keys.append(("paper", p)); texts.append(ft)
    keys.append(("gen", g["label"])); texts.append(g["essence"])
vecs = backend.embed(texts)
V = {k: unit(v) for k, v in zip(keys, vecs)}

print(f"[{KEY}] {'node':<40} {'cos_own':>8} {'margin':>8}  flag")
rows = []
# enrich-mode generator floors (paper centroids) double as sibling centroids at the gen grade
gen_floor_cents = {}
for g in reg["generators"]:
    if g.get("papers"):
        mem = [V[("paper", p)] for p in g["papers"] if ("paper", p) in V]
        gen_floor_cents[g["label"]] = centroid(mem)
for g in reg["generators"]:
    rung_cents = {}
    for r in g.get("rungs") or []:
        mem = [V[("paper", p)] for p in r["papers"] if ("paper", p) in V]
        rung_cents[r["name"]] = centroid(mem)
    for r in g.get("rungs") or []:
        own = rung_cents[r["name"]]
        if own is None:
            continue
        sv = V[("rung", f"{g['label']}|{r['name']}")]
        cos_own = dot(sv, own)
        sibs = [dot(sv, c) for n, c in rung_cents.items() if n != r["name"] and c is not None]
        margin = cos_own - max(sibs) if sibs else float("nan")
        rows.append((r["name"], cos_own, margin, len(r["papers"])))
    gv = V[("gen", g["label"])]
    if g.get("rungs"):
        # split: stated gen essence vs centroid of its rung essences
        rvecs = [V[("rung", f"{g['label']}|{r['name']}")] for r in g["rungs"]]
        cos_own = dot(gv, centroid(rvecs)) if rvecs else float("nan")
        rows.append((f"GEN {g['label'][:40]}", cos_own, float("nan"), len(g["rungs"])))
    else:
        # enrich: stated gen essence vs own paper-floor centroid, margin vs sibling gen floors
        own = gen_floor_cents.get(g["label"])
        if own is None:
            continue
        cos_own = dot(gv, own)
        sibs = [dot(gv, c) for lbl, c in gen_floor_cents.items()
                if lbl != g["label"] and c is not None]
        margin = cos_own - max(sibs) if sibs else float("nan")
        rows.append((f"GEN {g['label'][:40]}", cos_own, margin, len(g.get("papers") or [])))

for name, cos_own, margin, n in rows:
    flag = ""
    if cos_own < 0.55:
        flag = "LOW-FIT"
    if margin == margin and margin < 0.05:
        flag = (flag + " BLEED").strip()
    if n == 1:
        flag = (flag + " singleton").strip()
    print(f"{name:<46} {cos_own:>8.3f} {margin:>8.3f}  {flag}")
