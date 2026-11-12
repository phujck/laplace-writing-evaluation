"""THE TASTE RETURN LEG, demonstrated live on a real task context.
Reproduce: PYTHONPATH=src python3 scripts/demo_taste_return.py
"""
import json, re, sys

TARGET, GOAL, PROJECT = "s4", ("respine the estimates section so it earns the class "
                               "thesis; derivation placement and compression"), "paper_falqon"

def main():
    from laplace.pipeline import dispatch
    from laplace.engine import author_proxy, ruling_recall

    print("=" * 78)
    print("LEG 1 — THE BUILDER PROMPT (dispatch.compile_dispatch, worker=structure)")
    print("=" * 78)
    out = dispatch.compile_dispatch(TARGET, GOAL, worker="structure", project=PROJECT)
    p = out["prompt"]
    m = re.search(r"<!-- STANDING-RULINGS -->(.*?)<!-- /STANDING-RULINGS -->", p, re.S)
    print(f"prompt chars: {len(p)}   STANDING-RULINGS fence present: {bool(m)}")
    body = m.group(1)
    d = json.loads(body[body.index("{"):])
    for r in d["rulings"]:
        print(f"  {r['score']:.4f}  {r['ref']}")
        print(f"          [{r['kind'] or 'unkinded'} · {r['date']} · {r['confidence']}] "
              f"{r['ruling'][:120]}")
    print("  provenance:", json.dumps(d["provenance"], ensure_ascii=False))

    print()
    print("=" * 78)
    print("LEG 2 — THE PROXY FRAME (author_proxy.assemble_decision_frame)")
    print("=" * 78)
    q = ("DESLOP — the s4 register reads as slogan slop, and the derivation placement "
         "is unsettled: keep, kill, or rewrite, and does the derivation move to an "
         "appendix?")
    frame = author_proxy.assemble_decision_frame(".", q)
    print(f"prior_verdicts (the flat dump, unchanged): {len(frame['prior_verdicts'])}")
    print(f"relevant_rulings (the RECALLED slice):     {len(frame['relevant_rulings'])}")
    for r in frame["relevant_rulings"]:
        print(f"  {r['score']:.4f}  {r['ref']}  [{r['kind'] or 'unkinded'}]")
    print("  provenance:", json.dumps(frame["relevant_rulings_provenance"],
                                      ensure_ascii=False))

    print()
    print("=" * 78)
    print("LEG 3 — THE HONEST ABSENCE (a context his ledger is silent on)")
    print("=" * 78)
    silent = ruling_recall.recall(".", "hexadecimal palette for the sparkline widget "
                                       "gradient stops")
    print(ruling_recall.render_rows(silent, "WHAT HE HAS RULED"))

    print()
    print("=" * 78)
    print("LEG 4 — THE GAP-LEDGER BOOST (gap_ledger.rank_gaps prior_rulings, live)")
    print("=" * 78)
    from laplace.pipeline import detector_organs
    ev = detector_organs.run_detector_organs(PROJECT, root=".")
    pr = ev["gap_ledger"]["prior_rulings"]
    print(f"keys scanned: {len(pr['keys_scanned'])}   boosted: {len(pr['boost'])}")
    print(f"source: {pr['source']}")
    for g in ev["gap_ledger"]["capped_gaps"]:
        print(f"  boost={pr['boost'].get(g['id'], 0.0):.3f}  sev={g['severity']:.2f}  "
              f"{g['id']}  {(g['quote'] or g['issue'])[:56]}")

if __name__ == "__main__":
    sys.exit(main())
