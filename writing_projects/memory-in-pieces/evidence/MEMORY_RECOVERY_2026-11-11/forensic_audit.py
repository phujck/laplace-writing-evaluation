"""Forensic bookkeeping on an owner-stored snapshot, not a benchmark run.
No imports of benchmark code, network, subprocesses, models, or original-file writes."""
import argparse,json,re,hashlib
from pathlib import Path
from collections import Counter
p=argparse.ArgumentParser()
p.add_argument('--mode',required=True);p.add_argument('--args-json',required=True);p.add_argument('--result',required=True)
a=p.parse_args()
source=Path('evidence/MEMORY_RECOVERY_2026-11-11/forensic_input.json')
raw=source.read_bytes(); d=json.loads(raw)
def norm(s):
 for c in "‘’‚‛′´`":s=s.replace(c,"'")
 for c in '“”„‟″«»':s=s.replace(c,'"')
 return re.sub(r'\s+',' ',s).strip()
audit=[]
for x in d['x']:
 r=x['request'];sts=x['response']['statements'];got=[s['unit_id'] for s in sts];exp=r['unit_ids']
 same=sorted(got)==sorted(exp)
 pairs=[(uid,{s['unit_id']:s for s in sts}[uid]) for uid in exp] if same else list(zip(exp,sts))
 prompt=r['prompt'];scopes=json.loads(prompt[prompt.index('{"scopes":'):])['scopes']
 texts={u['unit_id']:u['text'] for sc in scopes for u in sc['units']}
 errors=[];kept=0;quotes=0;source_quote_matches=0;swaps=[]
 for uid,s in pairs:
  stored=x['processed'][uid]
  if stored['statement']!={f:(s.get(f) or '').strip() for f in ['subject','object','mechanism','conditions','consequences']}:errors.append({'uid':uid,'error':'field mapping differs'})
  for q in s['support_quotes']:
   quotes+=1;source_quote_matches+=norm(q) in norm(texts[uid])
  for w in stored['witnesses']:
   kept+=1
   if norm(w['text']) not in norm(texts[uid]):errors.append({'uid':uid,'error':'stored witness not in original request unit'})
   if w['start']<stored['start'] or w['end']>stored['end']:errors.append({'uid':uid,'error':'witness offsets escape source unit'})
   if w['end']-w['start']!=len(w['text']):errors.append({'uid':uid,'error':'witness span length differs'})
 for i,(uid,g) in enumerate(zip(exp,got)):
  if uid!=g:swaps.append({'position':i,'expected':uid,'returned':g,'original_source':texts[uid],'returned_fields':sts[i]})
 audit.append({'index':x['index'],'request_sha256':x['request_sha256'],'mode':'by-id' if same else 'position','units':len(exp),'returned':len(sts),'quotes':quotes,'quotes_in_source_units':source_quote_matches,'stored_witnesses':kept,'mapping_and_span_errors':errors,'mismatches':swaps})
ks={}
for key,v in d['k'].items():
 c={}
 for r in v['rows']:
  arm=str(r['set'])+'|'+str(r['key'])
  z=c.setdefault(arm,Counter())
  z['n']+=1;z['answered']+=r['has_answer'];z['three_votes']+=len(r['judge_votes'] or [])==3
  z['correct_true']+=r['correct'] is True;z['correct_false']+=r['correct'] is False;z['judgement_missing']+=r['correct'] is None
 ks[key]={'variant':v['variant'],'reader':v['reader'],'ledger':v['ledger'],'stop':v['stop'],'recorded_table':v['table'],'raw_bookkeeping':c,'failures':v['failures']}
b=d['b_ledger']
out={'schema_version':'memory-recovery-forensics/2','work_id':d['work_id'],'snapshot_sha256':hashlib.sha256(raw).hexdigest(),'x_alignment_audit':audit,'k_execution':ks,'longmem_raptor':{'attempts':len(b),'successes':sum(not r.get('failed') for r in b),'infrastructure_failures':sum(bool(r.get('failed')) for r in b),'unique_batches':len({r['batch_id'] for r in b})},'j_paired':d['j_paired'],'no_new_model_calls':True,'no_benchmark_reruns':True,'limitations':['Checks owner-stored snapshots pinned to original repository byte hashes and reading receipts.','Substring and interval checks do not establish all extracted fields semantically.','No independent reviewer judgement, held-out generalisation or new performance experiment is implied.','Original documents and evidence are not modified.']}
Path(a.result).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'anomalies':len(audit),'mapping_errors':sum(len(x['mapping_and_span_errors']) for x in audit),'raptor':out['longmem_raptor']}))
