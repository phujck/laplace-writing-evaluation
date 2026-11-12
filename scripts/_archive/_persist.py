"""Mechanical persist glue for the tranche-2 giant pour (no intelligence — routing only).

  slice: python _persist.py slice <task-output> <key> <A|B|C>
         -> _slices/<key>_<label>.json (grade-1 entity) + _gerard_chunks/<key>_<label>.json
  apex:  python _persist.py apex  <task-output> <key> <outfile.json>
         -> <outfile.json> (grade-2 apex) + _verdicts/<key>.json + appends adjudicator flags to _friction.md
"""
import json, sys, os

BASE = 'archive/soul_dump/_shard/scaled_tranche2_folded'

def load(out):
    env = json.loads(open(out, encoding='utf-8').read())
    r = env.get('result')
    return r if isinstance(r, dict) else json.loads(r)

def dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

mode, out = sys.argv[1], sys.argv[2]
if mode == 'slice':
    key, label = sys.argv[3], sys.argv[4]
    d = load(out); ent = d['entity']; gp = d.get('gerardParts', [])
    dump(ent, f'{BASE}/_slices/{key}_{label}.json')
    dump(gp,  f'{BASE}/_gerard_chunks/{key}_{label}.json')
    print(f"SLICE {key}_{label}: voice={len(ent.get('voice',[]))} history={len(ent.get('history',[]))} "
          f"relations={len(ent.get('relations',[]))} gerardParts={len(gp)} floor={d.get('n_floor')}/{d.get('n_batches')}")
elif mode == 'apex':
    key, outfile = sys.argv[3], sys.argv[4]
    d = load(out); apex = d['apex']; v = d['verdict']
    dump(apex, f'{BASE}/{outfile}')
    dump(v, f'{BASE}/_verdicts/{key}.json')
    with open(f'{BASE}/_friction.md', 'a', encoding='utf-8') as fp:
        fp.write(f"## {key} (apex adjudication flags — reconsolidation candidates, NOT patches)\n")
        for fl in v.get('flags', []):
            fp.write(f"- {str(fl)[:240]}\n")
        fp.write("\n")
    print(f"APEX {outfile}: voice={len(apex.get('voice',[]))} history={len(apex.get('history',[]))} "
          f"relations={len(apex.get('relations',[]))} conjectural={len(apex.get('conjectural',[]))} shards={len(apex.get('slice_shards',[]))}")
    print(f"VERDICT: {v.get('verdict')}")
    for k in ['faithful', 'partial', 'confabulated', 'seal_clean', 'detail_recoverable', 'history_salient', 'wrong_merges']:
        print(f"  {k}: {v.get(k)}")
elif mode == 'node':
    # single-run small person: the run IS the node (no slicing, no apex — never grew past usability)
    key = sys.argv[3]
    d = load(out); ent = d['entity']; gp = d.get('gerardParts', [])
    dump(ent, f'{BASE}/{key}.json')
    dump(gp,  f'{BASE}/_gerard_chunks/{key}.json')
    print(f"NODE {key}.json: voice={len(ent.get('voice',[]))} history={len(ent.get('history',[]))} "
          f"relations={len(ent.get('relations',[]))} gerardParts={len(gp)} floor={d.get('n_floor')}/{d.get('n_batches')}")
else:
    print("usage: _persist.py slice|apex|node <task-output> <key> <label|outfile>"); sys.exit(2)
